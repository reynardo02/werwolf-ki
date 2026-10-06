"""Prüft die Einstellungen einer neuen Partie – gemeinsam für Server und Browser-Version."""

from dataclasses import dataclass
from typing import Any

from werwolf.aufbau import NAMEN, SPIELERZAHL, VOLLMONDNACHT
from werwolf.vollmondnacht.rollen import szenario_namen


class Fehler(Exception):
    """Ungültige Einstellung: wird dem Browser als Meldung angezeigt."""


@dataclass(frozen=True)
class Einstellungen:
    regeln: str
    spieler: int
    llm: str  # Zahl oder "alle" (alle anderen Plätze)
    ich: str
    szenario: str | None

    @property
    def anzahl_llm(self) -> int:
        return self.spieler - 1 if self.llm == "alle" else int(self.llm)


def einstellungen_pruefen(daten: dict[str, Any]) -> Einstellungen:
    regeln = daten.get("regeln")
    if regeln not in SPIELERZAHL:
        raise Fehler(f"Unbekannte Regeln: {regeln}")
    try:
        spieler = int(daten.get("spieler", 7))
    except (TypeError, ValueError):
        raise Fehler("Spielerzahl muss eine Zahl sein") from None
    minimum, maximum = SPIELERZAHL[regeln]
    if not minimum <= spieler <= maximum:
        raise Fehler(f"Bei {regeln} sind {minimum} bis {maximum} Spieler möglich")
    llm = str(daten.get("llm", "alle"))
    if llm != "alle" and not (llm.isdigit() and int(llm) <= spieler - 1):
        raise Fehler(f"LLM-Spieler: 'alle' oder 0 bis {spieler - 1}")
    szenario = daten.get("szenario") or None
    if szenario is not None and (regeln != VOLLMONDNACHT or szenario not in szenario_namen(spieler)):
        raise Fehler(f"Szenario '{szenario}' passt nicht zu {regeln} mit {spieler} Spielern")
    ich = daten.get("ich") or NAMEN[0]
    if ich not in NAMEN[:spieler]:
        raise Fehler(f"Platz '{ich}' gibt es bei {spieler} Spielern nicht")
    return Einstellungen(regeln, spieler, llm, ich, szenario)


def optionen(spieler: int) -> dict[str, list[str]]:
    """Platz-Namen und Vollmondnacht-Szenarien für eine Spielerzahl (fürs Formular)."""
    return {
        "namen": NAMEN[:spieler] if spieler > 0 else [],
        "szenarien": szenario_namen(spieler) if 3 <= spieler <= 10 else [],
    }
