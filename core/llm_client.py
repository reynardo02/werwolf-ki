"""LLM-Clients: eine austauschbare Schnittstelle plus eine OpenAI-kompatible Umsetzung.

Das OpenAI-kompatible Format sprechen viele Anbieter (DeepSeek, Gemini, OpenRouter,
Ollama, ...). Den Anbieter wechselst du deshalb nur über `base_url` und `modell`.
Nur diese Datei kennt das SDK – der Rest des Projekts sieht nur `LLMClient`.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from core.tools import ToolCall, ToolSchema


class LLMFehler(Exception):
    """Der Anbieter hat einen Fehler gemeldet (Netzwerk, Key, Server, ...)."""


class BudgetErschoepft(Exception):
    """Das Limit an API-Aufrufen ist erreicht. Schützt vor unerwarteten Kosten."""


@dataclass
class Antwort:
    tool_call: ToolCall | None  # None: das Modell hat kein (lesbares) Tool aufgerufen
    text: str = ""  # Freitext, falls das Modell zusätzlich etwas geschrieben hat


@dataclass
class Statistik:
    aufrufe: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


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
    sdk: Any = None  # Nur für Tests: ein vorbereiteter openai.OpenAI-Client
    statistik: Statistik = field(default_factory=Statistik)

    def __post_init__(self) -> None:
        if self.sdk is None:
            self.sdk = openai.OpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=60, max_retries=2
            )

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        if self.statistik.aufrufe >= self.max_aufrufe:
            raise BudgetErschoepft(f"Limit von {self.max_aufrufe} API-Aufrufen erreicht.")
        self.statistik.aufrufe += 1

        try:
            antwort = self.sdk.chat.completions.create(
                model=self.modell,
                temperature=self.temperatur,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": nachricht},
                ],
                tools=[t.als_openai() for t in tools],
                tool_choice=self.tool_choice,
            )
        except openai.OpenAIError as fehler:
            raise LLMFehler(str(fehler)) from fehler

        if antwort.usage:
            self.statistik.input_tokens += antwort.usage.prompt_tokens or 0
            self.statistik.output_tokens += antwort.usage.completion_tokens or 0

        if not antwort.choices:
            return Antwort(None)
        nachricht_llm = antwort.choices[0].message
        return Antwort(_ersten_tool_call_lesen(nachricht_llm.tool_calls), nachricht_llm.content or "")


def _ersten_tool_call_lesen(tool_calls: list[Any] | None) -> ToolCall | None:
    """Nimmt den ersten Tool-Call. Kaputtes JSON zählt als 'kein Tool-Call'."""
    if not tool_calls:
        return None
    funktion = tool_calls[0].function
    try:
        argumente = json.loads(funktion.arguments or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(argumente, dict):
        return None
    return ToolCall(funktion.name, argumente)
