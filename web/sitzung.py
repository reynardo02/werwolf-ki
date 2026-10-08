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

from werwolf.aufbau import VOLLMONDNACHT
from werwolf.mensch_spieler import BESCHRIFTUNG
from werwolf.roles import Rolle as KlassischeRolle
from werwolf.schnittstelle import NACHT_WEITER, ZIEL_TOOLS, Aktion, Ereignis, Zug
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
            "text": tool not in zug.optionen and tool not in ZIEL_TOOLS and tool != NACHT_WEITER,
        })
    vollmond = isinstance(zug.rolle, VollmondRolle)
    return {
        "wer": zug.ich,  # mehrere Menschen an einem Gerät: Wem wird das Gerät gereicht?
        "phase": zug.phase.value,
        "rolle": zug.rolle.value,
        "rolle_titel": "Deine Karte zu Beginn" if vollmond else "Deine Rolle",
        "geheimwissen": list(zug.geheimwissen),
        "hinweis": zug.hinweis,
        "tools": tools,
    }


def geheimes(engine: Any, menschen: tuple[str, ...]) -> dict[str, Any]:
    """Was nur die Menschen wissen – live aus der Engine, nicht erst bei ihrem nächsten Zug.

    So sieht z. B. der Räuber schon morgens, vor dem Chat, welche Karte er jetzt hat.
    """
    return {
        "geheimwissen": {m: engine.wissen(m) for m in menschen},
        "jetzt_karten": {m: k for m in menschen if (k := engine.bekannte_karte(m))},
    }


def karte_titel(regeln: str) -> str:
    return "Deine Karte zu Beginn" if regeln == VOLLMONDNACHT else "Deine Rolle"


class WebSpieler:
    """Agent, dessen Züge aus dem Browser kommen – für alle menschlichen Plätze zugleich."""

    def __init__(self) -> None:
        self._antworten: queue.Queue[Aktion | None] = queue.Queue()
        self.frage: dict[str, Any] | None = None
        # Laufende Nummer: Zwei gleich aussehende Fragen (z. B. zweimal „Etwas sagen“)
        # muss der Browser trotzdem als neue Frage erkennen.
        self._nummer = 0
        self._lock = threading.Lock()

    def handeln(self, zug: Zug) -> Aktion:
        with self._lock:
            self._nummer += 1
            self.frage = frage_aus_zug(zug) | {"nummer": self._nummer}
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
    """Eine laufende Partie mit einem oder mehreren Menschen (an einem Gerät)."""

    regeln: str
    spieler: int
    llm: str  # Zahl oder "alle"
    menschen: tuple[str, ...]
    szenario: str | None = None
    namen: tuple[str, ...] = ()  # alle Spieler in Sitzreihenfolge (leer: Platz-Namen)
    ordner: Path | None = None  # Standard: logs/ wie bei main.py
    seed: int = field(default_factory=lambda: random.randrange(1_000_000))
    ereignisse: list[dict[str, str]] = field(default_factory=list)
    ende: str | None = None
    fehler: str | None = None
    gewonnen: dict[str, bool] = field(default_factory=dict)  # Mensch -> gewonnen?, nach dem Spielende
    karten: dict[str, str] = field(default_factory=dict)  # Mensch -> Karte bzw. Rolle, ab dem Austeilen
    mensch: WebSpieler = field(default_factory=WebSpieler)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._engine: Any = None  # ab dem Austeilen: für Wissen und Karten der Menschen
        self.dateiname = f"partie_{datetime.now():%Y%m%d_%H%M%S}_web"

    def _beobachten(self, ereignis: Ereignis) -> None:
        if ereignis.oeffentlich:  # Geheimes (Nachtaktionen, Begründungen) nie an den Browser
            with self._lock:
                self.ereignisse.append({"phase": ereignis.phase.value, "art": ereignis.art, "text": ereignis.text})
                if ereignis.art == "spielende":
                    if "sieger" in ereignis.daten:  # Vollmondnacht nennt die Sieger direkt
                        sieger = ereignis.daten["sieger"].split(", ")
                        self.gewonnen = {m: m in sieger for m in self.menschen}
                    else:  # klassisch: Team der eigenen Rolle
                        gewinner = ereignis.daten.get("gewinner")
                        self.gewonnen = {
                            m: KlassischeRolle(k).team.value == gewinner for m, k in self.karten.items()
                        }

    def _engine_gebaut(self, engine: Any, rolle_von: dict[str, str]) -> None:
        with self._lock:
            self._engine = engine
            # Nur die der Menschen – die übrigen bleiben geheim.
            self.karten = {m: rolle_von[m] for m in self.menschen}

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._spielen, daemon=True)
        self._thread.start()

    def _spielen(self) -> None:
        # Erst hier importieren: main.py importiert seinerseits viel, und so bleibt
        # die Sitzung ohne LLM-Konfiguration testbar.
        from main import partie_spielen
        from core.konfig import konfig_laden

        try:
            anzahl_llm = self.spieler - len(self.menschen) if self.llm == "alle" else int(self.llm)
            client = konfig_laden().client() if anzahl_llm else None
            kurz = partie_spielen(
                self.seed, self.spieler, anzahl_llm, client, self.dateiname, ausfuehrlich=False,
                regeln=self.regeln, szenario=self.szenario, menschen=self.menschen, mensch_spieler=self.mensch,
                beobachter_extra=self._beobachten, konsole=False, engine_gebaut=self._engine_gebaut, namen=self.namen or None,
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
                "menschen": list(self.menschen),
                "seed": self.seed,
                "ereignisse": self.ereignisse[seit:],
                "anzahl": len(self.ereignisse),
                "frage": self.mensch.frage,
                **(geheimes(self._engine, self.menschen) if self._engine
                   else {"geheimwissen": {}, "jetzt_karten": {}}),
                "karten": dict(self.karten),
                "karte_titel": karte_titel(self.regeln),
                "ende": self.ende,
                "gewonnen": dict(self.gewonnen),
                "fehler": self.fehler,
                "protokoll": f"logs/{self.dateiname}.txt" if self.ende else None,
            }

    def antworten(self, tool: str, parameter: dict[str, str]) -> bool:
        return self.mensch.antworten(Aktion(tool, parameter))

    def beenden(self) -> None:
        if self._thread and self._thread.is_alive():
            self.mensch.abbrechen()
