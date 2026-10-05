import random
from collections.abc import Callable

import pytest

from werwolf.engine import Engine
from werwolf.mock_agent import MockAgent
from werwolf.roles import Rolle, Team
from werwolf.schnittstelle import ABSTIMMEN, OPFER_WAEHLEN, PRUEFEN, Aktion, Phase, Zug

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]

# Feste Rollen für Tests: Anna und Ben sind Werwölfe, Clara ist Seherin.
ROLLEN = {
    "Anna": Rolle.WERWOLF,
    "Ben": Rolle.WERWOLF,
    "Clara": Rolle.SEHERIN,
    "Dario": Rolle.DORFBEWOHNER,
    "Emil": Rolle.DORFBEWOHNER,
    "Frieda": Rolle.DORFBEWOHNER,
    "Greta": Rolle.DORFBEWOHNER,
}


class SkriptAgent:
    """Testagent: Eine Funktion entscheidet, was er tut. Merkt sich jeden Zug."""

    def __init__(self, entscheiden: Callable[[Zug], Aktion]) -> None:
        self.entscheiden = entscheiden
        self.zuege: list[Zug] = []

    def handeln(self, zug: Zug) -> Aktion:
        self.zuege.append(zug)
        return self.entscheiden(zug)


def mock_engine(seed: int, anzahl: int = 7) -> Engine:
    rng = random.Random(seed)
    agenten = {name: MockAgent(random.Random(rng.random())) for name in NAMEN[:anzahl]}
    return Engine(agenten, rng=rng)


@pytest.mark.parametrize("anzahl", [5, 6, 7])
def test_100_zufallspartien(anzahl: int) -> None:
    """Meilenstein-1-Kriterium: 100 Zufallspartien laufen fehlerfrei durch."""
    for seed in range(100):
        engine = mock_engine(seed, anzahl)
        ergebnis = engine.spielen()

        # Das gemeldete Ergebnis muss zur tatsächlichen Lage passen.
        assert engine.sieger() is ergebnis.gewinner
        woelfe = [n for n in ergebnis.ueberlebende if engine.spieler[n].rolle is Rolle.WERWOLF]
        if ergebnis.gewinner is Team.DORF:
            assert woelfe == []
        else:
            assert len(woelfe) >= len(ergebnis.ueberlebende) - len(woelfe)


def test_gleicher_seed_gleiche_partie() -> None:
    e1, e2 = mock_engine(42), mock_engine(42)
    e1.spielen()
    e2.spielen()
    assert [e.text for e in e1.protokoll] == [e.text for e in e2.protokoll]


def test_werwoelfe_kennen_sich_seherin_nicht() -> None:
    engine = Engine({n: MockAgent() for n in NAMEN}, rollen=ROLLEN)
    assert engine.spieler["Anna"].geheimwissen == ["Ben ist Werwolf (Mitspieler)."]
    assert engine.spieler["Ben"].geheimwissen == ["Anna ist Werwolf (Mitspieler)."]
    assert engine.spieler["Clara"].geheimwissen == []


def test_siegbedingungen() -> None:
    engine = Engine({n: MockAgent() for n in NAMEN}, rollen=ROLLEN)
    assert engine.sieger() is None

    # 2 Werwölfe gegen 2 Dorfbewohner: Werwölfe gewinnen.
    for name in ["Clara", "Dario", "Emil"]:
        engine.spieler[name].lebendig = False
    assert engine.sieger() is Team.WERWOELFE

    # Alle Werwölfe tot: Dorf gewinnt.
    for name in NAMEN:
        engine.spieler[name].lebendig = name not in ("Anna", "Ben")
    assert engine.sieger() is Team.DORF


def test_ungueltige_aktion_zweiter_versuch_dann_zufall() -> None:
    """Ein Agent, der nur Unsinn liefert, wird zweimal gefragt, dann entscheidet der Zufall."""
    trottel = SkriptAgent(lambda zug: Aktion("fliegen", {}))
    agenten = {n: MockAgent(random.Random(i)) for i, n in enumerate(NAMEN)}
    agenten["Dario"] = trottel
    engine = Engine(agenten, rng=random.Random(0), rollen=ROLLEN)
    engine.spielen()

    # Zweiter Versuch bekommt den Hinweis, erster nicht.
    assert trottel.zuege[0].hinweis is None
    assert trottel.zuege[1].hinweis is not None
    assert "fliegen" in trottel.zuege[1].hinweis
    # Trotz des Unsinns hat Dario gesprochen (Zufallsaktion).
    assert any(e.text == 'Dario: "(schweigt)"' for e in engine.protokoll)


def test_werwolf_darf_keinen_werwolf_waehlen() -> None:
    assert Engine._pruefen(Aktion(OPFER_WAEHLEN, {"ziel": "Ben"}), OPFER_WAEHLEN, ["Clara"])
    assert Engine._pruefen(Aktion(OPFER_WAEHLEN, {"ziel": "Clara"}), OPFER_WAEHLEN, ["Clara"]) is None


def test_falsches_tool_wird_abgelehnt() -> None:
    assert Engine._pruefen(Aktion(PRUEFEN, {"ziel": "Ben"}), ABSTIMMEN, ["Ben"]) is not None


def test_leerer_text_wird_abgelehnt() -> None:
    assert Engine._pruefen(Aktion("sprechen", {"text": "  "}), "sprechen", []) is not None


def gezielt(nacht: str, pruefung: str, stimme: Callable[[Zug], str]) -> Callable[[Zug], Aktion]:
    """Baut eine Entscheidungsfunktion mit festen Zielen je Phase."""

    def entscheiden(zug: Zug) -> Aktion:
        tool = zug.erlaubte_tools[0]
        if tool == OPFER_WAEHLEN:
            return Aktion(tool, {"ziel": nacht})
        if tool == PRUEFEN:
            return Aktion(tool, {"ziel": pruefung})
        if tool == ABSTIMMEN:
            return Aktion(tool, {"ziel": stimme(zug)})
        return Aktion(tool, {"text": "Hallo."})

    return entscheiden


def test_eine_runde_im_detail() -> None:
    # Werwölfe fressen Dario, Seherin prüft Anna, alle stimmen gegen Anna,
    # nur Anna selbst stimmt für Emil.
    entscheiden = gezielt("Dario", "Anna", lambda z: "Emil" if z.ich == "Anna" else "Anna")
    agenten = {n: SkriptAgent(entscheiden) for n in NAMEN}
    engine = Engine(agenten, rng=random.Random(0), rollen=ROLLEN)

    engine.runde = 1
    engine._nacht()
    assert not engine.spieler["Dario"].lebendig
    assert "Runde 1: Anna ist Werwolf." in engine.spieler["Clara"].geheimwissen

    engine._diskussion()
    # 6 Lebende x 2 Sprechrunden
    reden = [e for e in engine.protokoll if e.phase is Phase.DISKUSSION]
    assert len(reden) == 12

    engine._abstimmung()
    assert not engine.spieler["Anna"].lebendig
    assert engine.sieger() is None

    # Tote werden nicht mehr gefragt.
    anzahl_vorher = len(agenten["Dario"].zuege)
    engine._rundenende()
    assert len(agenten["Dario"].zuege) == anzahl_vorher
    assert engine.spieler["Clara"].notizen == ["Runde 1: Hallo."]


def test_gleichstand_niemand_scheidet_aus() -> None:
    # Anna, Ben und Clara stimmen für Emil, die anderen drei für Anna: 3:3.
    def stimme(zug: Zug) -> str:
        return "Emil" if zug.ich in ("Anna", "Ben", "Clara") else "Anna"

    agenten = {n: SkriptAgent(gezielt("Greta", "Ben", stimme)) for n in NAMEN}
    engine = Engine(agenten, rng=random.Random(0), rollen=ROLLEN)
    engine.runde = 1
    engine._nacht()  # Greta stirbt, 6 bleiben: 3 Stimmen Emil, 3 Stimmen Anna
    engine._abstimmung()

    assert engine.spieler["Anna"].lebendig
    assert engine.spieler["Emil"].lebendig
    assert engine.protokoll[-1].text == "Gleichstand – niemand scheidet aus."


def test_agenten_sehen_keine_geheimen_ereignisse() -> None:
    agenten = {n: MockAgent(random.Random(i)) for i, n in enumerate(NAMEN)}
    beobachter = SkriptAgent(agenten["Greta"].handeln)
    agenten["Greta"] = beobachter
    engine = Engine(agenten, rng=random.Random(0), rollen=ROLLEN)
    engine.spielen()

    for zug in beobachter.zuege:
        assert all(e.oeffentlich for e in zug.ereignisse)
        assert not any("Werwolf) wählt" in e.text for e in zug.ereignisse)


def test_notizen_und_begruendungen_nur_im_geheimen_protokoll() -> None:
    engine = mock_engine(7)
    engine.spielen()
    geheim = [e.text for e in engine.protokoll if not e.oeffentlich]
    assert any(t.startswith("Notiz ") for t in geheim)
    assert any(t.startswith("Begründung ") for t in geheim)
    assert not any(e.text.startswith(("Notiz ", "Begründung ")) for e in engine.protokoll if e.oeffentlich)


ARTEN = {
    "runde", "opfer_vorschlag", "begruendung", "pruefung", "tod", "rede", "stimme",
    "gleichstand", "notiz", "ungueltig", "zufallsaktion", "spielende",
}


def test_jedes_ereignis_hat_art_und_daten() -> None:
    for seed in range(20):
        engine = mock_engine(seed)
        ergebnis = engine.spielen()
        assert {e.art for e in engine.protokoll} <= ARTEN

        ende = engine.protokoll[-1]
        assert ende.art == "spielende" and ende.daten["gewinner"] == ergebnis.gewinner.value
        for e in engine.protokoll:
            if e.art == "tod":
                assert e.daten["rolle"] == engine.spieler[e.daten["name"]].rolle.value
                assert e.daten["ursache"] in ("nacht", "abstimmung")
            if e.art == "stimme":
                assert e.daten["ziel"] in engine.spieler and e.daten["von"] != e.daten["ziel"]
