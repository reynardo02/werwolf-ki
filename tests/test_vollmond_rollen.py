import random
from collections import Counter

import pytest

from werwolf.vollmondnacht.rollen import (
    ANARCHIE,
    SCHACHTEL,
    SZENARIEN,
    Partei,
    Rolle,
    gewinner_bestimmen,
    szenario_karten,
    szenario_namen,
)

W, D, G, GE = Rolle.WERWOLF, Rolle.DORFBEWOHNER, Rolle.GUENSTLING, Rolle.GERBER
DORF, RUDEL, GERBER = Partei.DORF, Partei.WERWOELFE, Partei.GERBER


def test_alle_szenarien_haben_drei_karten_mehr_und_passen_in_die_schachtel() -> None:
    schachtel = Counter(SCHACHTEL)
    assert len(SCHACHTEL) == 16
    for name, (_, zusaetze) in SZENARIEN.items():
        for anzahl in zusaetze:
            karten = szenario_karten(name, anzahl, random.Random(0))
            assert len(karten) == anzahl + 3, (name, anzahl)
            assert not Counter(karten) - schachtel, f"{name} mit {anzahl}: Karten fehlen in der Schachtel"


def test_anarchie() -> None:
    for anzahl in range(3, 11):
        karten = szenario_karten(ANARCHIE, anzahl, random.Random(anzahl))
        assert len(karten) == anzahl + 3
        assert karten.count(W) == 2 and D in karten
        assert not Counter(karten) - Counter(SCHACHTEL)


def test_szenario_namen_nach_spielerzahl() -> None:
    assert "Wiedergänger" in szenario_namen(8)
    assert "Wiedergänger" not in szenario_namen(7)
    assert ANARCHIE in szenario_namen(5)


def test_falsche_spielerzahl() -> None:
    with pytest.raises(ValueError):
        szenario_karten("Einsame Nacht", 7, random.Random(0))


def test_parteien() -> None:
    assert W.partei is RUDEL and G.partei is RUDEL
    assert GE.partei is GERBER
    assert Rolle.SEHERIN.partei is DORF and Rolle.JAEGER.partei is DORF


# Jeder Pfad des Entscheidungsbaums vom Spielleiterbogen.
@pytest.mark.parametrize("endrollen, tote, gewinner", [
    # Niemand stirbt
    ({"A": W, "B": D, "C": D}, set(), {RUDEL}),
    ({"A": D, "B": D, "C": D}, set(), {DORF}),
    # Gerber stirbt
    ({"A": GE, "B": W, "C": D}, {"A"}, {GERBER}),
    ({"A": GE, "B": W, "C": D}, {"A", "B"}, {GERBER, DORF}),
    # Werwolf stirbt (auch wenn zusätzlich ein Dorfbewohner stirbt)
    ({"A": W, "B": D, "C": D}, {"A"}, {DORF}),
    ({"A": W, "B": D, "C": D}, {"A", "B"}, {DORF}),
    # Günstling stirbt
    ({"A": G, "B": W, "C": D}, {"A"}, {RUDEL}),
    ({"A": G, "B": D, "C": D}, {"A"}, {DORF}),
    # Unschuldiger stirbt
    ({"A": W, "B": D, "C": D}, {"B"}, {RUDEL}),
    ({"A": G, "B": D, "C": D}, {"B"}, {RUDEL}),  # Günstling ohne Werwölfe überlebt
    ({"A": D, "B": D, "C": D}, {"B"}, set()),  # niemand gewinnt
])
def test_wer_hat_gewonnen(endrollen, tote, gewinner) -> None:
    assert gewinner_bestimmen(endrollen, tote) == gewinner
