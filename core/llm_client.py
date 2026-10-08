"""LLM-Clients: eine austauschbare Schnittstelle plus eine OpenAI-kompatible Umsetzung.

Das OpenAI-kompatible Format sprechen viele Anbieter (DeepSeek, Gemini, OpenRouter,
Ollama, ...). Den Anbieter wechselst du deshalb nur über `base_url` und `modell`.
Nur diese Datei kennt das SDK – der Rest des Projekts sieht nur `LLMClient`.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from core.schnittstellen import CHAT, RESPONSES, anfrage_bauen, antwort_lesen
from core.tools import ToolCall, ToolSchema


class LLMFehler(Exception):
    """Der Anbieter hat einen Fehler gemeldet (Netzwerk, Key, Server, ...)."""


class BudgetErschoepft(Exception):
    """Das Limit an API-Aufrufen ist erreicht. Schützt vor unerwarteten Kosten."""


class KontingentErschoepft(Exception):
    """Der Anbieter sperrt für lange Zeit, z. B. weil das Tageslimit erreicht ist.

    Absichtlich KEIN LLMFehler: Ein LLMFehler wird zur Zufallsaktion, hier soll
    die Partie aber abbrechen, statt nur noch zufällig weiterzuspielen.
    """


# Länger als so viele Sekunden zu warten lohnt sich nicht, dann wird abgebrochen.
MAX_WARTEZEIT = 300.0


def wartezeit_aus_fehler(text: str) -> float | None:
    """Liest aus einer 429-Meldung, wie lange der Anbieter sperrt (in Sekunden).

    Gemini schreibt z. B. "retryDelay': '41195s'". Unbekanntes Format: None.
    """
    treffer = re.search(r"retryDelay\W+(\d+(?:\.\d+)?)s", text)
    return float(treffer.group(1)) if treffer else None


@dataclass
class Antwort:
    tool_call: ToolCall | None  # None: das Modell hat kein (lesbares) Tool aufgerufen
    text: str = ""  # Freitext, falls das Modell zusätzlich etwas geschrieben hat


@dataclass
class Statistik:
    aufrufe: int = 0
    input_tokens: int = 0
    gecachte_tokens: int = 0  # Teil der input_tokens, den der Anbieter aus dem Cache billiger berechnet
    output_tokens: int = 0
    fehler: int = 0  # Aufrufe, bei denen der Anbieter einen Fehler gemeldet hat
    ohne_tool_call: int = 0  # Antworten ohne (lesbaren) Tool-Call
    letzter_fehler: str = ""
    gewartet: float = 0.0  # Sekunden, die wegen Tempolimit oder 429 gewartet wurden


class LLMClient(Protocol):
    """Alles, was diese Methode hat, kann als LLM dienen – auch ein Test-Fake."""

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort: ...


@dataclass
class OpenAIKompatiblerClient:
    base_url: str
    modell: str
    api_key: str
    temperatur: float = 0.9
    max_aufrufe: int = 400
    # "required" zwingt das Modell zu einem Tool-Call. Manche lokalen Modelle
    # kennen das nicht – dann in der .env auf "auto" stellen.
    tool_choice: str = "required"
    # Höchstens so viele Anfragen pro Minute (0 = kein Limit). Kostenlose Tarife
    # erlauben oft nur wenige, z. B. 15 bei Gemini.
    max_pro_minute: int = 0
    # Wie oft nach "429 Too Many Requests" gewartet und neu versucht wird.
    versuche_bei_limit: int = 3
    # "chat" (/chat/completions, versteht fast jeder Anbieter) oder "responses" (/responses,
    # OpenAI): GPT-6-Modelle nutzen Tools beim Nachdenken nur über /responses.
    schnittstelle: str = CHAT
    sdk: Any = None  # Nur für Tests: ein vorbereiteter openai.OpenAI-Client
    statistik: Statistik = field(default_factory=Statistik)
    # Uhr und Warten sind austauschbar, damit Tests nicht wirklich warten müssen.
    uhr: Callable[[], float] = time.monotonic
    schlafen: Callable[[float], None] = time.sleep
    _letzte_anfrage: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.sdk is None:
            self.sdk = openai.OpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=60, max_retries=2
            )

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        if self.statistik.aufrufe >= self.max_aufrufe:
            raise BudgetErschoepft(f"Limit von {self.max_aufrufe} API-Aufrufen erreicht.")
        self.statistik.aufrufe += 1

        anfrage = {"model": self.modell} | anfrage_bauen(
            self.schnittstelle, system, nachricht, tools, self.tool_choice, self.temperatur
        )
        senden = self.sdk.responses.create if self.schnittstelle == RESPONSES else self.sdk.chat.completions.create
        for versuch in range(self.versuche_bei_limit + 1):
            self._tempo_einhalten()
            try:
                antwort = senden(**anfrage)
                break
            except openai.RateLimitError as fehler:
                # Lange Sperre (z. B. Tageslimit): Warten bringt nichts, abbrechen.
                sperre = wartezeit_aus_fehler(str(fehler))
                if "PerDay" in str(fehler) or (sperre is not None and sperre > MAX_WARTEZEIT):
                    self._fehler_melden(fehler)
                    raise KontingentErschoepft(str(fehler)) from fehler
                # Zu viele Anfragen pro Minute: kurz warten, dann neu versuchen.
                if versuch == self.versuche_bei_limit:
                    raise self._fehler_melden(fehler) from fehler
                self._warten(min(60.0, 10.0 * 2**versuch))
            except openai.OpenAIError as fehler:
                raise self._fehler_melden(fehler) from fehler

        # Beide Formate über dieselbe Übersetzung lesen (core/schnittstellen.py).
        tool_call, text, nutzung = antwort_lesen(antwort.model_dump())
        self.statistik.input_tokens += nutzung.input_tokens
        self.statistik.output_tokens += nutzung.output_tokens
        self.statistik.gecachte_tokens += nutzung.gecachte_tokens  # nicht jeder Anbieter meldet den Cache
        if tool_call is None:
            self.statistik.ohne_tool_call += 1
        return Antwort(tool_call, text)

    def _tempo_einhalten(self) -> None:
        """Wartet, bis seit der letzten Anfrage genug Zeit vergangen ist."""
        if self.max_pro_minute > 0 and self._letzte_anfrage is not None:
            abstand = 60.0 / self.max_pro_minute
            rest = self._letzte_anfrage + abstand - self.uhr()
            if rest > 0:
                self._warten(rest)
        self._letzte_anfrage = self.uhr()

    def _warten(self, sekunden: float) -> None:
        self.statistik.gewartet += sekunden
        self.schlafen(sekunden)

    def _fehler_melden(self, fehler: openai.OpenAIError) -> LLMFehler:
        self.statistik.fehler += 1
        self.statistik.letzter_fehler = str(fehler)
        return LLMFehler(str(fehler))
