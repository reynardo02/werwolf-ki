"""Nachts reihum: Menschen, die sich ein Gerät teilen, kommen alle genau einmal dran.

Sonst verriete die Reihenfolge (Doppelgängerin zuerst, dann Seherin …) oder das Überspringen
ihre Rolle. Die Regeln dürfen sich dadurch nicht ändern: Gleiche Entscheidungen müssen genau
dasselbe Ergebnis liefern wie ohne `nacht_reihum`.
"""

import random

import pytest

from werwolf.engine import Engine
from werwolf.roles import Rolle as KlassischeRolle
from werwolf.schnittstelle import NACHT_WEITER, SPRECHEN, Aktion, Phase, Zug
from werwolf.vollmondnacht.engine import VollmondEngine
from werwolf.vollmondnacht.rollen import Rolle, szenario_karten

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta", "Hugo"]


class Erster:
    """Wählt immer das erste Tool und die ersten erlaubten (verschiedenen) Werte – ohne Zufall,
    damit beide Abläufe dieselben Entscheidungen treffen. Schreibt mit, wer wann gefragt wurde."""

    def __init__(self, fragen: list[tuple[str, Phase, str]]) -> None:
        self.fragen = fragen

    def handeln(self, zug: Zug) -> Aktion:
        tool = zug.erlaubte_tools[0]
        self.fragen.append((zug.ich, zug.phase, tool))
        if tool == SPRECHEN:
            return Aktion(tool, {"text": "Hallo."})
        if tool in zug.optionen:
            parameter: dict[str, str] = {}
            for name, werte in zug.optionen[tool].items():
                parameter[name] = next(w for w in werte if w not in parameter.values())
            return Aktion(tool, parameter)
        ziele = zug.ziele or [n for n in zug.lebende if n != zug.ich]
        return Aktion(tool, {"ziel": ziele[0]})


def vollmond(seed: int, reihum: tuple[str, ...]) -> tuple[VollmondEngine, list]:
    fragen: list = []
    agent = Erster(fragen)
    karten = szenario_karten("Wiedergänger", 8, random.Random(seed))  # fast alle Rollen, mit Doppelgängerin
    engine = VollmondEngine({n: agent for n in NAMEN}, karten, rng=random.Random(seed), nacht_reihum=reihum)
    engine.spielen()
    return engine, fragen


@pytest.mark.parametrize("seed", range(12))
def test_vollmond_gleiches_ergebnis_andere_reihenfolge(seed: int) -> None:
    menschen = ("Ben", "Clara", "Emil", "Greta")
    normal, _ = vollmond(seed, ())
    reihum, fragen = vollmond(seed, menschen)

    # Regeln unverändert: gleiche Endkarten, gleiches Wissen, gleiche Nachtaktionen.
    assert reihum.endrollen() == normal.endrollen() and reihum.mitte == normal.mitte
    assert {n: s.wissen for n, s in reihum.spieler.items()} == {n: s.wissen for n, s in normal.spieler.items()}
    aktionen = lambda e: sorted(str(x.daten) for x in e.protokoll if x.art == "nacht_aktion")  # noqa: E731
    assert aktionen(reihum) == aktionen(normal)

    # Nachts: Jeder Mensch kommt dran, in Sitzreihenfolge, ohne Lücke für Rollen ohne Aktion.
    nacht = [wer for wer, phase, _ in fragen if phase is Phase.NACHT and wer in menschen]
    ohne_wiederholung = [w for i, w in enumerate(nacht) if i == 0 or nacht[i - 1] != w]
    assert ohne_wiederholung == list(menschen)  # nur die Doppelgängerin fragt zweimal hintereinander
    for wer, phase, tool in fragen:
        if tool == NACHT_WEITER:
            assert wer in menschen and reihum.spieler[wer].startrolle not in (
                Rolle.DOPPELGAENGERIN, Rolle.SEHERIN, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN)
    # Die Menschen sind vor allen anderen dran: Niemand muss zwischendurch warten.
    erste = [wer for wer, phase, _ in fragen if phase is Phase.NACHT][:len(nacht)]
    assert set(erste) <= set(menschen)


def test_vollmond_ohne_reihum_kein_nacht_weiter() -> None:
    _, fragen = vollmond(3, ())
    assert not any(tool == NACHT_WEITER for _, _, tool in fragen)


def test_klassisch_reihum_jeder_lebende_mensch_jede_nacht() -> None:
    fragen: list = []
    agent = Erster(fragen)
    rollen = {"Anna": KlassischeRolle.DORFBEWOHNER, "Ben": KlassischeRolle.WERWOLF,
              "Clara": KlassischeRolle.SEHERIN, "Dario": KlassischeRolle.WERWOLF,
              "Emil": KlassischeRolle.DORFBEWOHNER, "Frieda": KlassischeRolle.DORFBEWOHNER}
    menschen = ("Anna", "Ben", "Clara", "Emil")
    engine = Engine({n: agent for n in rollen}, rng=random.Random(2), rollen=rollen, nacht_reihum=menschen)
    engine.spielen()

    nacht = [(wer, tool) for wer, phase, tool in fragen if phase is Phase.NACHT]
    # Erste Nacht: alle leben, Sitzreihenfolge; Menschen ohne Aktion bekommen „nacht_weiter“.
    assert nacht[:5] == [("Anna", NACHT_WEITER), ("Ben", "opfer_waehlen"), ("Clara", "pruefen"),
                         ("Dario", "opfer_waehlen"), ("Emil", NACHT_WEITER)]
    assert "Frieda" not in [wer for wer, _ in nacht]  # kein Mensch, keine Aktion: nicht gefragt
