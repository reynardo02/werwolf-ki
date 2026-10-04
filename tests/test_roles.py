import random

import pytest

from werwolf.roles import Rolle, Team, rollen_verteilen


@pytest.mark.parametrize("anzahl, werwoelfe", [(5, 1), (6, 2), (7, 2)])
def test_rollenverteilung(anzahl: int, werwoelfe: int) -> None:
    namen = [f"S{i}" for i in range(anzahl)]
    rollen = rollen_verteilen(namen, random.Random(0))

    assert set(rollen) == set(namen)
    werte = list(rollen.values())
    assert werte.count(Rolle.WERWOLF) == werwoelfe
    assert werte.count(Rolle.SEHERIN) == 1
    assert werte.count(Rolle.DORFBEWOHNER) == anzahl - werwoelfe - 1


def test_zu_wenige_spieler() -> None:
    with pytest.raises(ValueError):
        rollen_verteilen(["A", "B", "C", "D"], random.Random(0))


def test_doppelte_namen() -> None:
    with pytest.raises(ValueError):
        rollen_verteilen(["A", "A", "B", "C", "D"], random.Random(0))


def test_teams() -> None:
    assert Rolle.WERWOLF.team is Team.WERWOELFE
    assert Rolle.SEHERIN.team is Team.DORF
    assert Rolle.DORFBEWOHNER.team is Team.DORF
