"""Werwolf im Browser (Pyodide): Wiederholen statt Warten.

Im Browser kann Python nicht blockierend warten – weder auf deinen Klick noch auf
die Antwort des LLM. Unsere Partien sind aber reproduzierbar: Gleicher Seed und
gleiche Antworten ergeben genau denselben Verlauf. Deshalb läuft es so:

  1. `schritt()` spielt die Partie von vorn, bis eine Antwort fehlt.
  2. Fehlt dein Zug, kommt die Frage zurück; fehlt eine LLM-Antwort, die Anfrage.
  3. JavaScript besorgt die Antwort (Klick bzw. fetch mit deinem API-Key),
     hängt sie an die Liste an und ruft `schritt()` erneut auf.

Jede Wiederholung dauert nur Millisekunden, denn alle Antworten liegen dann schon vor.
Der API-Key kommt nie in Python an: Die Anfrage an den Anbieter schickt JavaScript.
"""

import json
import random
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

try:
    import openai  # noqa: F401 – nur prüfen, ob es das SDK gibt
except ImportError:
    # Im Browser gibt es das openai-SDK nicht. core/llm_client.py importiert es aber,
    # weil der Konsolen-Client es braucht. Hier genügt ein leerer Platzhalter: Der
    # Browser schickt seine Anfragen selbst (siehe WiederholClient).
    _platzhalter = types.ModuleType("openai")
    _platzhalter.OpenAIError = type("OpenAIError", (Exception,), {})
    _platzhalter.RateLimitError = type("RateLimitError", (_platzhalter.OpenAIError,), {})
    sys.modules["openai"] = _platzhalter

from core.llm_client import Antwort  # noqa: E402 – erst nach dem Platzhalter importieren
from core.tools import ToolCall, ToolSchema  # noqa: E402
from web.einstellungen import Fehler, einstellungen_pruefen, optionen  # noqa: E402
from web.sitzung import frage_aus_zug, karte_titel  # noqa: E402
from werwolf.aufbau import (  # noqa: E402
    NAMEN,
    VOLLMONDNACHT,
    agenten_bauen,
    engine_bauen,
    ergebnis_zusammenfassen,
    kopf_bauen,
    protokoll_kopf,
)
from werwolf.engine import Engine  # noqa: E402
from werwolf.jsonl_log import JsonlLog  # noqa: E402
from werwolf.protokoll import Protokoll  # noqa: E402
from werwolf.schnittstelle import Aktion, Ereignis, Zug  # noqa: E402
from werwolf.vollmondnacht.engine import VollmondErgebnis  # noqa: E402
from werwolf.vollmondnacht.rollen import szenario_namen  # noqa: E402


class BrauchtEingabe(Exception):
    """Dein Zug fehlt noch."""

    def __init__(self, frage: dict[str, Any]) -> None:
        self.frage = frage


class BrauchtLLM(Exception):
    """Eine LLM-Antwort fehlt noch. `anfrage` ist der Körper für /chat/completions."""

    def __init__(self, anfrage: dict[str, Any]) -> None:
        self.anfrage = anfrage


class WiederholSpieler:
    """Alle Menschen: gibt der Reihe nach die bisherigen Antworten zurück, danach fragt er.

    Eine Liste reicht auch für mehrere Menschen: Die Engine fragt bei gleichem Seed
    und gleichen Antworten immer in derselben Reihenfolge.
    """

    def __init__(self, antworten: list[dict[str, Any]]) -> None:
        self.antworten = antworten
        self.i = 0
        self.geheimwissen: dict[str, list[str]] = {}  # Platz -> zuletzt bekanntes Geheimwissen

    def handeln(self, zug: Zug) -> Aktion:
        self.geheimwissen[zug.ich] = list(zug.geheimwissen)
        if self.i < len(self.antworten):
            antwort = self.antworten[self.i]
            self.i += 1
            return Aktion(str(antwort["tool"]), {k: str(v) for k, v in (antwort.get("parameter") or {}).items()})
        # Die Nummer zählt deine Züge: So erkennt der Browser auch zwei gleich aussehende Fragen.
        raise BrauchtEingabe(frage_aus_zug(zug) | {"nummer": self.i + 1})


class WiederholClient:
    """LLM-Client mit gespeicherten Antworten. Fehlt eine, wird die Anfrage gemeldet."""

    def __init__(self, modell: str, antworten: list[dict[str, Any]], temperatur: float = 0.9) -> None:
        self.modell = modell
        self.antworten = antworten
        self.temperatur = temperatur
        self.i = 0

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        if self.i < len(self.antworten):
            antwort = antwort_aus_json(self.antworten[self.i])
            self.i += 1
            return antwort
        # Gleiches Format wie OpenAIKompatiblerClient – nur ohne Modell und Key,
        # die setzt JavaScript ein.
        raise BrauchtLLM({
            "temperature": self.temperatur,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": nachricht}],
            "tools": [t.als_openai() for t in tools],
            "tool_choice": "required",
        })


def antwort_aus_json(daten: dict[str, Any]) -> Antwort:
    """Liest eine rohe /chat/completions-Antwort. Kaputtes zählt als „kein Tool-Call“."""
    try:
        nachricht = daten["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return Antwort(None)
    text = nachricht.get("content") or ""
    tool_calls = nachricht.get("tool_calls") or []
    if not tool_calls:
        return Antwort(None, text)
    funktion = tool_calls[0].get("function") or {}
    try:
        argumente = json.loads(funktion.get("arguments") or "{}")
    except json.JSONDecodeError:
        return Antwort(None, text)
    if not isinstance(argumente, dict):
        return Antwort(None, text)
    return Antwort(ToolCall(str(funktion.get("name")), argumente), text)


def _gewonnen(ergebnis: Any, engine: Any, menschen: tuple[str, ...]) -> dict[str, bool]:
    if isinstance(ergebnis, VollmondErgebnis):
        return {m: m in ergebnis.sieger for m in menschen}
    assert isinstance(engine, Engine)
    return {m: engine.spieler[m].rolle.team == ergebnis.gewinner for m in menschen}


def _log_text(kopf: dict[str, Any], ereignisse: list[Ereignis], daten: dict[str, Any]) -> str:
    """Das JSONL-Log als Text – im Browser gibt es kein logs/, also zum Herunterladen."""
    with tempfile.TemporaryDirectory() as ordner:
        pfad = Path(ordner) / "partie.jsonl"
        log = JsonlLog(pfad, kopf)
        for e in ereignisse:
            log(e)
        log.eintrag("ergebnis", **daten, api=None)
        log.schliessen()
        return pfad.read_text(encoding="utf-8")


def schritt(
    einstellungen: dict[str, Any], seed: int, antworten_mensch: list[dict[str, Any]],
    antworten_llm: list[dict[str, Any]], modell: str = "",
) -> dict[str, Any]:
    """Spielt die Partie von vorn bis zur ersten fehlenden Antwort (oder bis zum Ende)."""
    e = einstellungen_pruefen(einstellungen)
    rng = random.Random(seed)
    namen = NAMEN[:e.spieler]
    szenario = e.szenario
    if e.regeln == VOLLMONDNACHT and szenario is None:
        szenario = szenario_namen(e.spieler)[0]

    mensch = WiederholSpieler(antworten_mensch)
    client = WiederholClient(modell, antworten_llm) if e.anzahl_llm else None
    besetzung = agenten_bauen(seed, rng, namen, e.anzahl_llm, client, e.regeln, e.menschen, mensch)
    alle: list[Ereignis] = []
    engine, rolle_von = engine_bauen(e.regeln, besetzung.agenten, rng, szenario or "", alle.append)

    zustand: dict[str, Any] = {
        "menschen": list(e.menschen), "seed": seed, "frage": None, "llm_anfrage": None,
        "ende": None, "gewonnen": {}, "protokoll": None, "log": None,
    }
    try:
        ergebnis = engine.spielen()
    except BrauchtEingabe as b:
        zustand["frage"] = b.frage
    except BrauchtLLM as b:
        zustand["llm_anfrage"] = b.anfrage
    else:
        kurz, zeilen, daten = ergebnis_zusammenfassen(ergebnis)
        zustand["ende"] = kurz
        zustand["gewonnen"] = _gewonnen(ergebnis, engine, e.menschen)
        kopf = kopf_bauen(e.regeln, modell or None, seed, namen, rolle_von, besetzung, engine, szenario)
        protokoll = Protokoll(ausgabe=None)
        protokoll.kopf(*protokoll_kopf(kopf))
        for ereignis in alle:
            protokoll(ereignis)
        protokoll.schreiben()
        for zeile in zeilen:
            protokoll.schreiben(zeile)
        zustand["protokoll"] = protokoll.text()
        zustand["log"] = _log_text(kopf, alle, daten)

    # Nur Öffentliches – wie beim Server sieht der Browser nie fremde Geheimnisse.
    zustand["ereignisse"] = [
        {"phase": x.phase.value, "art": x.art, "text": x.text} for x in alle if x.oeffentlich
    ]
    zustand["geheimwissen"] = mensch.geheimwissen
    zustand["karten"] = {m: rolle_von[m] for m in e.menschen}  # nur die der Menschen
    zustand["karte_titel"] = karte_titel(e.regeln)
    return zustand


# --- Schnittstelle für JavaScript: JSON rein, JSON raus -------------------------

def schritt_json(eingabe: str) -> str:
    daten = json.loads(eingabe)
    try:
        zustand = schritt(
            daten["einstellungen"], int(daten["seed"]), daten.get("antworten_mensch", []),
            daten.get("antworten_llm", []), daten.get("modell", ""),
        )
    except Fehler as fehler:
        return json.dumps({"fehler": str(fehler)}, ensure_ascii=False)
    return json.dumps(zustand, ensure_ascii=False)


def optionen_json(spieler: int) -> str:
    return json.dumps(optionen(spieler), ensure_ascii=False)


def einstellungen_json(eingabe: str) -> str:
    """Prüft nur die Einstellungen: {"ok": true} oder {"fehler": "..."}."""
    try:
        einstellungen_pruefen(json.loads(eingabe))
    except Fehler as fehler:
        return json.dumps({"fehler": str(fehler)}, ensure_ascii=False)
    return json.dumps({"ok": True})
