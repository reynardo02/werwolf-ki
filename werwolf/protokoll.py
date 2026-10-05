"""Lesbares Spielprotokoll: gegliedert nach Runde und Phase, mit geheimen Infos."""

from collections.abc import Callable
from pathlib import Path

from werwolf.schnittstelle import Ereignis, Phase


class Protokoll:
    """Sammelt das Protokoll als Text und gibt jede Zeile sofort aus.

    Als `beobachter` an die Engine übergeben. Geheime Ereignisse (Nachtaktionen,
    Begründungen, Notizen) werden eingerückt markiert – so sieht man, wo ein
    Spieler öffentlich etwas anderes sagt, als er denkt.
    """

    def __init__(self, ausgabe: Callable[[str], None] | None = print) -> None:
        self.ausgabe = ausgabe
        self.zeilen: list[str] = []
        self._abschnitt: tuple[int, Phase] | None = None

    def schreiben(self, zeile: str = "") -> None:
        self.zeilen.append(zeile)
        if self.ausgabe:
            self.ausgabe(zeile)

    def kopf(self, titel: str, besetzung: list[str]) -> None:
        self.schreiben(titel)
        self.schreiben("=" * len(titel))
        for eintrag in besetzung:
            self.schreiben(f"- {eintrag}")

    def __call__(self, ereignis: Ereignis) -> None:
        # Neue Überschrift, sobald Runde oder Phase wechseln.
        if self._abschnitt != (ereignis.runde, ereignis.phase):
            if self._abschnitt is None or self._abschnitt[0] != ereignis.runde:
                self.schreiben()
                self.schreiben(f"=== Runde {ereignis.runde} ===")
            self.schreiben(f"--- {ereignis.phase.value} ---")
            self._abschnitt = (ereignis.runde, ereignis.phase)

        praefix = "" if ereignis.oeffentlich else "    [geheim] "
        self.schreiben(f"{praefix}{ereignis.text}")

    def text(self) -> str:
        return "\n".join(self.zeilen) + "\n"

    def speichern(self, pfad: Path) -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(self.text(), encoding="utf-8")
