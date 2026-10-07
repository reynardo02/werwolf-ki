"""Prüft die Einstellungen einer neuen Partie – gemeinsam für Server und Browser-Version."""

from dataclasses import dataclass
from typing import Any

from werwolf.aufbau import NAMEN, SPIELERZAHL, VOLLMONDNACHT
from werwolf.vollmondnacht.rollen import szenario_namen


# Mehr Menschen an einem Gerät werden unübersichtlich (jeder Zug braucht eine Übergabe).
MAX_MENSCHEN = 5


class Fehler(Exception):
    """Ungültige Einstellung: wird dem Browser als Meldung angezeigt."""


@dataclass(frozen=True)
class Einstellungen:
    regeln: str
    spieler: int
    llm: str  # Zahl oder "alle" (alle Plätze ohne Mensch)
    menschen: tuple[str, ...]  # Plätze, an denen Menschen spielen (an einem Gerät)
    szenario: str | None

    @property
    def anzahl_llm(self) -> int:
        return self.spieler - len(self.menschen) if self.llm == "alle" else int(self.llm)


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
    # „ich“ ist das alte Format mit genau einem Menschen (gespeicherte Partien im Browser).
    menschen = daten.get("menschen") or [daten.get("ich") or NAMEN[0]]
    if not isinstance(menschen, list) or not all(isinstance(m, str) for m in menschen):
        raise Fehler("Menschen: Liste von Platz-Namen erwartet")
    falsch = [m for m in menschen if m not in NAMEN[:spieler]]
    if falsch:
        raise Fehler(f"Platz '{falsch[0]}' gibt es bei {spieler} Spielern nicht")
    if len(set(menschen)) != len(menschen):
        raise Fehler("Jeder Platz kann nur einmal von einem Menschen besetzt werden")
    if len(menschen) > min(MAX_MENSCHEN, spieler):
        raise Fehler(f"Höchstens {min(MAX_MENSCHEN, spieler)} Menschen bei {spieler} Spielern")
    frei = spieler - len(menschen)
    llm = str(daten.get("llm", "alle"))
    if llm != "alle" and not (llm.isdigit() and int(llm) <= frei):
        raise Fehler(f"LLM-Spieler: 'alle' oder 0 bis {frei}")
    szenario = daten.get("szenario") or None
    if szenario is not None and (regeln != VOLLMONDNACHT or szenario not in szenario_namen(spieler)):
        raise Fehler(f"Szenario '{szenario}' passt nicht zu {regeln} mit {spieler} Spielern")
    # In Sitzreihenfolge: So kommen die Übergaben in der Reihenfolge, in der die Engine fragt.
    return Einstellungen(regeln, spieler, llm, tuple(n for n in NAMEN[:spieler] if n in menschen), szenario)


def optionen(spieler: int) -> dict[str, list[str]]:
    """Platz-Namen und Vollmondnacht-Szenarien für eine Spielerzahl (fürs Formular)."""
    return {
        "namen": NAMEN[:spieler] if spieler > 0 else [],
        "szenarien": szenario_namen(spieler) if 3 <= spieler <= 10 else [],
    }
