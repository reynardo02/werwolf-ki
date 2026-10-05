"""Ein Spieler, der seine Züge per Tastatur eingibt (Meilenstein 5).

Er bedient dieselbe Schnittstelle wie MockAgent und LLMSpieler: Zug rein, Aktion raus.
Was öffentlich am Tisch passiert, zeigt main.py live an. Dieser Spieler zeigt nur,
was die anderen nicht sehen: deine Rolle, dein Geheimwissen und die Frage, was du tust.

Ein- und Ausgabe sind austauschbar (Standard: input/print), damit Tests ohne
Tastatur auskommen.
"""

from collections.abc import Callable

from werwolf.schnittstelle import (
    ABSTIMMEN,
    NOTIZ_SCHREIBEN,
    OPFER_WAEHLEN,
    PRUEFEN,
    SPRECHEN,
    ZIEL_TOOLS,
    Aktion,
    Zug,
)
from werwolf.vollmondnacht.engine import (
    MITTE_ANSEHEN,
    NACHAHMEN,
    NICHTS_TUN,
    RAUBEN,
    SPIELER_ANSEHEN,
    VERTAUSCHEN,
)

# Was jedes Tool am Tisch bedeutet, für das Auswahlmenü.
BESCHRIFTUNG = {
    SPRECHEN: "Etwas sagen",
    ABSTIMMEN: "Abstimmen: Wer soll sterben?",
    OPFER_WAEHLEN: "Opfer wählen",
    PRUEFEN: "Einen Spieler prüfen",
    NOTIZ_SCHREIBEN: "Notiz für dich (Enter = keine)",
    NACHAHMEN: "Karte eines Mitspielers ansehen und nachahmen",
    SPIELER_ANSEHEN: "Karte eines Mitspielers ansehen",
    MITTE_ANSEHEN: "Zwei Karten aus der Mitte ansehen",
    RAUBEN: "Karte eines Mitspielers rauben",
    VERTAUSCHEN: "Karten von zwei Mitspielern vertauschen",
    NICHTS_TUN: "Nichts tun",
}


class MenschSpieler:
    def __init__(
        self,
        eingabe: Callable[[str], str] = input,
        ausgabe: Callable[[str], None] = print,
    ) -> None:
        self.eingabe = eingabe
        self.ausgabe = ausgabe
        self._gezeigt: set[str] = set()  # Geheimwissen, das schon angezeigt wurde

    def handeln(self, zug: Zug) -> Aktion:
        self._lage_zeigen(zug)
        tool = self._tool_waehlen(zug)
        return Aktion(tool, self._parameter_abfragen(zug, tool))

    # ------------------------------------------------------------------

    def _lage_zeigen(self, zug: Zug) -> None:
        self.ausgabe("")
        self.ausgabe(f">>> {zug.ich}, du bist dran ({zug.phase.value}). Deine Karte zu Beginn: {zug.rolle.value}")
        # Nur Neues zeigen, sonst wiederholt sich das Wissen bei jedem Zug.
        neu = [w for w in zug.geheimwissen if w not in self._gezeigt]
        for wissen in neu:
            self.ausgabe(f"    Nur für dich: {wissen}")
        self._gezeigt.update(neu)
        if zug.hinweis:
            self.ausgabe(f"    Ungültig: {zug.hinweis}")

    def _tool_waehlen(self, zug: Zug) -> str:
        if len(zug.erlaubte_tools) == 1:
            return zug.erlaubte_tools[0]
        beschriftungen = [BESCHRIFTUNG.get(t, t) for t in zug.erlaubte_tools]
        index = self._auswahl("Was tust du?", beschriftungen)
        return zug.erlaubte_tools[index]

    def _parameter_abfragen(self, zug: Zug, tool: str) -> dict[str, str]:
        if tool in zug.optionen:
            # Mehrere Parameter (z. B. ziel1, ziel2) oder gar keine (nichts_tun).
            # Schon Gewähltes wird nicht nochmal angeboten: Die Unruhestifterin
            # braucht zwei verschiedene Spieler.
            parameter: dict[str, str] = {}
            for name, werte in zug.optionen[tool].items():
                frei = [w for w in werte if w not in parameter.values()] or werte
                parameter[name] = frei[self._auswahl(f"{BESCHRIFTUNG.get(tool, tool)} – {name}:", frei)]
            return parameter
        if tool in ZIEL_TOOLS:
            ziele = zug.ziele or [n for n in zug.lebende if n != zug.ich]
            return {"ziel": ziele[self._auswahl(BESCHRIFTUNG.get(tool, tool), ziele)]}
        return {"text": self._text_abfragen(tool)}

    def _text_abfragen(self, tool: str) -> str:
        while True:
            text = self.eingabe(f"{BESCHRIFTUNG.get(tool, tool)}: ").strip()
            if text:
                return text
            if tool == NOTIZ_SCHREIBEN:
                return "(keine Notiz)"
            self.ausgabe("Bitte gib etwas ein.")

    def _auswahl(self, frage: str, moeglichkeiten: list[str]) -> int:
        """Fragt so lange, bis eine Nummer oder ein passender Name eingegeben wird."""
        self.ausgabe(frage)
        for i, m in enumerate(moeglichkeiten, start=1):
            self.ausgabe(f"  {i}) {m}")
        while True:
            antwort = self.eingabe("Deine Wahl: ").strip()
            if antwort.isdigit() and 1 <= int(antwort) <= len(moeglichkeiten):
                return int(antwort) - 1
            treffer = [i for i, m in enumerate(moeglichkeiten) if m.lower() == antwort.lower()]
            if treffer:
                return treffer[0]
            self.ausgabe(f"Bitte eine Zahl von 1 bis {len(moeglichkeiten)} oder einen Namen eingeben.")
