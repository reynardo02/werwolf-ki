"""Eine Partie im Hintergrund, die der Browser abfragt und steuert.

Die Engine ist synchron: Sie ruft `agent.handeln(zug)` auf und wartet auf die Antwort.
Für den Browser läuft die Partie deshalb in einem eigenen Thread. Ist der Mensch dran,
legt `WebSpieler` die Frage ab und wartet, bis über `antworten()` eine Aktion kommt.
Der Browser holt sich regelmäßig den `zustand()` – das nennt man Polling.

Wichtig: Der Browser bekommt nur öffentliche Ereignisse und dein eigenes Geheimwissen.
"""

import queue
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from werwolf.mensch_spieler import BESCHRIFTUNG
from werwolf.schnittstelle import ZIEL_TOOLS, Aktion, Ereignis, Zug
from werwolf.vollmondnacht.rollen import Rolle as VollmondRolle


class Abgebrochen(Exception):
    """Beendet eine wartende Partie, z. B. wenn eine neue gestartet wird."""


def frage_aus_zug(zug: Zug) -> dict[str, Any]:
    """Übersetzt einen Zug in JSON für den Browser: was du siehst und was du tun darfst."""
    tools = []
    for tool in zug.erlaubte_tools:
        if tool in zug.optionen:
            parameter = zug.optionen[tool]
        elif tool in ZIEL_TOOLS:
            parameter = {"ziel": zug.ziele or [n for n in zug.lebende if n != zug.ich]}
        else:
            parameter = {}
        tools.append({
            "name": tool,
            "beschriftung": BESCHRIFTUNG.get(tool, tool),
            "parameter": parameter,
            # Tools ohne feste Werte und ohne Parameter-Liste brauchen einen Freitext.
            "text": tool not in zug.optionen and tool not in ZIEL_TOOLS,
        })
    vollmond = isinstance(zug.rolle, VollmondRolle)
    return {
        "phase": zug.phase.value,
        "rolle": zug.rolle.value,
        "rolle_titel": "Deine Karte zu Beginn" if vollmond else "Deine Rolle",
        "geheimwissen": list(zug.geheimwissen),
        "hinweis": zug.hinweis,
        "tools": tools,
    }


class WebSpieler:
    """Agent, dessen Züge aus dem Browser kommen."""

    def __init__(self) -> None:
        self._antworten: queue.Queue[Aktion | None] = queue.Queue()
        self.frage: dict[str, Any] | None = None
        self.geheimwissen: list[str] = []
        self._lock = threading.Lock()

    def handeln(self, zug: Zug) -> Aktion:
        with self._lock:
            self.frage = frage_aus_zug(zug)
            self.geheimwissen = list(zug.geheimwissen)
        aktion = self._antworten.get()  # wartet auf den Browser
        if aktion is None:
            raise Abgebrochen()
        return aktion

    def antworten(self, aktion: Aktion) -> bool:
        """Nimmt genau eine Antwort pro offener Frage an – ein Doppelklick im Browser
        darf nicht versehentlich schon den nächsten Zug beantworten."""
        with self._lock:
            if self.frage is None:
                return False
            self.frage = None
        self._antworten.put(aktion)
        return True

    def abbrechen(self) -> None:
        self._antworten.put(None)


@dataclass
class Sitzung:
    """Eine laufende Partie mit dir als Spieler."""

    regeln: str
    spieler: int
    llm: str  # Zahl oder "alle"
    ich: str
    szenario: str | None = None
    ordner: Path | None = None  # Standard: logs/ wie bei main.py
    seed: int = field(default_factory=lambda: random.randrange(1_000_000))
    ereignisse: list[dict[str, str]] = field(default_factory=list)
    ende: str | None = None
    fehler: str | None = None
    mensch: WebSpieler = field(default_factory=WebSpieler)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.dateiname = f"partie_{datetime.now():%Y%m%d_%H%M%S}_web"

    def _beobachten(self, ereignis: Ereignis) -> None:
        if ereignis.oeffentlich:  # Geheimes (Nachtaktionen, Begründungen) nie an den Browser
            with self._lock:
                self.ereignisse.append({"phase": ereignis.phase.value, "art": ereignis.art, "text": ereignis.text})

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._spielen, daemon=True)
        self._thread.start()

    def _spielen(self) -> None:
        # Erst hier importieren: main.py importiert seinerseits viel, und so bleibt
        # die Sitzung ohne LLM-Konfiguration testbar.
        from main import partie_spielen
        from core.konfig import konfig_laden

        try:
            anzahl_llm = self.spieler - 1 if self.llm == "alle" else int(self.llm)
            client = konfig_laden().client() if anzahl_llm else None
            kurz = partie_spielen(
                self.seed, self.spieler, anzahl_llm, client, self.dateiname, ausfuehrlich=False,
                regeln=self.regeln, szenario=self.szenario, mensch=self.ich, mensch_spieler=self.mensch,
                beobachter_extra=self._beobachten, konsole=False,
                **({"ordner": self.ordner} if self.ordner else {}),
            )
            with self._lock:
                self.ende = kurz
        except Abgebrochen:
            with self._lock:
                self.ende = "abgebrochen"
        except Exception as fehler:  # z. B. fehlende .env oder API-Fehler: im Browser anzeigen
            with self._lock:
                self.fehler = f"{type(fehler).__name__}: {fehler}"

    def zustand(self, seit: int = 0) -> dict[str, Any]:
        """Alles, was der Browser anzeigen darf. `seit`: nur Ereignisse ab dieser Nummer."""
        with self._lock:
            return {
                "ich": self.ich,
                "seed": self.seed,
                "ereignisse": self.ereignisse[seit:],
                "anzahl": len(self.ereignisse),
                "frage": self.mensch.frage,
                "geheimwissen": self.mensch.geheimwissen,
                "ende": self.ende,
                "fehler": self.fehler,
                "protokoll": f"logs/{self.dateiname}.txt" if self.ende else None,
            }

    def antworten(self, tool: str, parameter: dict[str, str]) -> bool:
        return self.mensch.antworten(Aktion(tool, parameter))

    def beenden(self) -> None:
        if self._thread and self._thread.is_alive():
            self.mensch.abbrechen()
