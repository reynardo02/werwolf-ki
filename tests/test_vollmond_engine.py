import random

import pytest

from werwolf.mock_agent import MockAgent
from werwolf.schnittstelle import ABSTIMMEN, SPRECHEN, Aktion, Zug
from werwolf.vollmondnacht.engine import (
    MITTE_ANSEHEN,
    NACHAHMEN,
    RAUBEN,
    SPIELER_ANSEHEN,
    VERTAUSCHEN,
    VollmondEngine,
)
from werwolf.vollmondnacht.rollen import Partei, Rolle, szenario_karten, szenario_namen

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta", "Hugo", "Ida", "Jonas"]
R = Rolle


class Skript:
    """Testagent: legt fest, was in welcher Situation getan wird, und merkt sich die Züge."""

    def __init__(self, nacht: Aktion | None = None, stimme: str = "", text: str = "Hallo.") -> None:
        self.nacht, self.stimme, self.text = nacht, stimme, text
        self.zuege: list[Zug] = []

    def handeln(self, zug: Zug) -> Aktion:
        self.zuege.append(zug)
        tool = zug.erlaubte_tools[0]
        if tool == SPRECHEN:
            return Aktion(SPRECHEN, {"text": self.text})
        if tool == ABSTIMMEN:
            return Aktion(ABSTIMMEN, {"ziel": self.stimme})
        # Ohne Vorgabe ungültig: Die Engine wählt dann eine Zufallsaktion.
        return self.nacht or Aktion("")


def engine(verteilung: dict[str, Rolle], mitte: list[Rolle], agenten: dict[str, Skript]) -> VollmondEngine:
    karten = list(verteilung.values()) + mitte
    return VollmondEngine(agenten, karten, rng=random.Random(0), verteilung=verteilung, mitte=mitte)


def alle_stimmen_fuer(ziel: str, namen: list[str], ausnahme: str) -> dict[str, Skript]:
    return {n: Skript(stimme=ausnahme if n == ziel else ziel) for n in namen}


@pytest.mark.parametrize("anzahl", range(3, 11))
def test_viele_zufallspartien_in_allen_szenarien(anzahl: int) -> None:
    for name in szenario_namen(anzahl):
        for seed in range(15):
            rng = random.Random(seed)
            karten = szenario_karten(name, anzahl, rng)
            agenten = {n: MockAgent(random.Random(rng.random())) for n in NAMEN[:anzahl]}
            e = VollmondEngine(agenten, karten, rng=rng)
            ergebnis = e.spielen()

            # Karten gehen nie verloren: Spieler + Mitte = alle Karten.
            assert sorted(list(e.karten.values()) + e.mitte, key=str) == sorted(karten, key=str)
            assert all(e.endrollen()[s].partei in ergebnis.gewinner for s in ergebnis.sieger)
            assert e.protokoll[-1].art == "spielende"


def test_werwoelfe_kennen_sich_und_seherin_sieht_karte() -> None:
    verteilung = {"Anna": R.WERWOLF, "Ben": R.WERWOLF, "Clara": R.SEHERIN, "Dario": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Anna", list(verteilung), "Ben")
    agenten["Clara"].nacht = Aktion(SPIELER_ANSEHEN, {"ziel": "Ben"})
    e = engine(verteilung, [R.DORFBEWOHNER, R.RAEUBER, R.UNRUHESTIFTERIN], agenten)
    ergebnis = e.spielen()

    assert "Die Werwölfe sind: Anna, Ben." in e.spieler["Anna"].wissen
    assert "Du hast die Karte von Ben angesehen: Werwolf." in e.spieler["Clara"].wissen
    # Anna hat 3 Stimmen und stirbt, sie ist Werwolf: Das Dorf gewinnt.
    assert ergebnis.tote == ["Anna"]
    assert ergebnis.gewinner == {Partei.DORF}
    assert set(ergebnis.sieger) == {"Clara", "Dario"}


def test_seherin_mitte_und_einsamer_wolf() -> None:
    verteilung = {"Anna": R.WERWOLF, "Ben": R.SEHERIN, "Clara": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Anna")
    agenten["Ben"].nacht = Aktion(MITTE_ANSEHEN)
    e = engine(verteilung, [R.WERWOLF, R.RAEUBER, R.UNRUHESTIFTERIN], agenten)
    ergebnis = e.spielen()

    assert any(w.startswith("Du bist der einzige Werwolf") for w in e.spieler["Anna"].wissen)
    assert any(w.startswith("Du hast zwei Karten aus der Mitte") for w in e.spieler["Ben"].wissen)
    assert ergebnis.gewinner == {Partei.WERWOELFE} and ergebnis.sieger == ["Anna"]


def test_raeuber_wechselt_die_partei() -> None:
    verteilung = {"Anna": R.WERWOLF, "Ben": R.RAEUBER, "Clara": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Anna", list(verteilung), "Clara")
    agenten["Ben"].nacht = Aktion(RAUBEN, {"ziel": "Anna"})
    e = engine(verteilung, [R.DORFBEWOHNER, R.SEHERIN, R.UNRUHESTIFTERIN], agenten)
    ergebnis = e.spielen()

    assert e.karten == {"Anna": R.RAEUBER, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER}
    assert "Deine neue Karte: Werwolf" in e.spieler["Ben"].wissen[-1]
    # Anna stirbt, ist aber jetzt Räuberin (Dorf). Ben ist der Werwolf und lebt.
    assert ergebnis.gewinner == {Partei.WERWOELFE} and ergebnis.sieger == ["Ben"]


def test_unruhestifterin_und_schlaflose() -> None:
    verteilung = {"Anna": R.UNRUHESTIFTERIN, "Ben": R.SCHLAFLOSE, "Clara": R.WERWOLF}
    agenten = alle_stimmen_fuer("Ben", list(verteilung), "Clara")
    agenten["Anna"].nacht = Aktion(VERTAUSCHEN, {"ziel1": "Ben", "ziel2": "Clara"})
    e = engine(verteilung, [R.DORFBEWOHNER, R.SEHERIN, R.RAEUBER], agenten)
    e.spielen()

    assert e.karten["Ben"] is R.WERWOLF and e.karten["Clara"] is R.SCHLAFLOSE
    # Die Schlaflose wacht nach der Unruhestifterin auf und sieht ihre neue Karte.
    assert "Am Ende der Nacht liegt diese Karte vor dir: Werwolf." in e.spieler["Ben"].wissen
    # Am Tag weiß sie es auch strukturiert – der LLM-Spieler wechselt damit die Seite.
    tageszuege = [z for z in agenten["Ben"].zuege if z.erlaubte_tools[0] == SPRECHEN]
    assert tageszuege and all(z.bekannte_karte is R.WERWOLF for z in tageszuege)
    assert agenten["Anna"].zuege[-1].bekannte_karte is None  # kennt ihre Karte nicht


def test_unruhestifterin_braucht_zwei_verschiedene_ziele() -> None:
    verteilung = {"Anna": R.UNRUHESTIFTERIN, "Ben": R.DORFBEWOHNER, "Clara": R.WERWOLF}
    agenten = alle_stimmen_fuer("Ben", list(verteilung), "Clara")
    agenten["Anna"].nacht = Aktion(VERTAUSCHEN, {"ziel1": "Ben", "ziel2": "Ben"})
    e = engine(verteilung, [R.DORFBEWOHNER, R.SEHERIN, R.RAEUBER], agenten)
    e.spielen()
    assert agenten["Anna"].zuege[1].hinweis == "Du musst zwei verschiedene Spieler wählen."
    # Danach Zufallsaktion: Nichtstun gibt es nicht, also vertauscht sie die beiden anderen.
    assert e.karten == {"Anna": R.UNRUHESTIFTERIN, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER}


def test_betrunkener_tauscht_mit_der_mitte() -> None:
    verteilung = {"Anna": R.BETRUNKENER, "Ben": R.DORFBEWOHNER, "Clara": R.WERWOLF}
    e = engine(verteilung, [R.SEHERIN, R.SEHERIN, R.SEHERIN], alle_stimmen_fuer("Ben", list(verteilung), "Clara"))
    e.spielen()
    assert e.karten["Anna"] is R.SEHERIN and R.BETRUNKENER in e.mitte


def test_gleichstand_alle_sterben_und_jeder_eine_stimme_niemand() -> None:
    verteilung = {"Anna": R.WERWOLF, "Ben": R.DORFBEWOHNER, "Clara": R.DORFBEWOHNER, "Dario": R.DORFBEWOHNER}
    mitte = [R.SEHERIN, R.RAEUBER, R.UNRUHESTIFTERIN]
    # 2:2 zwischen Anna und Ben: beide sterben, ein Werwolf ist dabei.
    stimmen = {"Anna": "Ben", "Ben": "Anna", "Clara": "Anna", "Dario": "Ben"}
    ergebnis = engine(verteilung, mitte, {n: Skript(stimme=z) for n, z in stimmen.items()}).spielen()
    assert ergebnis.tote == ["Anna", "Ben"] and ergebnis.gewinner == {Partei.DORF}

    # Ringstimmen: jeder genau 1 Stimme, niemand stirbt, der Werwolf gewinnt.
    ring = {"Anna": "Ben", "Ben": "Clara", "Clara": "Dario", "Dario": "Anna"}
    ergebnis = engine(verteilung, mitte, {n: Skript(stimme=z) for n, z in ring.items()}).spielen()
    assert ergebnis.tote == [] and ergebnis.gewinner == {Partei.WERWOELFE}


def test_jaeger_reisst_sein_ziel_mit() -> None:
    verteilung = {"Anna": R.JAEGER, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER}
    stimmen = {"Anna": "Ben", "Ben": "Anna", "Clara": "Anna"}
    ergebnis = engine(verteilung, [R.SEHERIN, R.RAEUBER, R.UNRUHESTIFTERIN],
                      {n: Skript(stimme=z) for n, z in stimmen.items()}).spielen()
    assert ergebnis.tote == ["Anna", "Ben"] and ergebnis.gewinner == {Partei.DORF}


def test_gerber_gewinnt_allein() -> None:
    verteilung = {"Anna": R.GERBER, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER}
    ergebnis = engine(verteilung, [R.SEHERIN, R.RAEUBER, R.UNRUHESTIFTERIN],
                      alle_stimmen_fuer("Anna", list(verteilung), "Clara")).spielen()
    assert ergebnis.gewinner == {Partei.GERBER} and ergebnis.sieger == ["Anna"]


def test_guenstling_und_freimaurer() -> None:
    verteilung = {"Anna": R.GUENSTLING, "Ben": R.WERWOLF, "Clara": R.FREIMAURER, "Dario": R.FREIMAURER}
    e = engine(verteilung, [R.WERWOLF, R.SEHERIN, R.RAEUBER], alle_stimmen_fuer("Clara", list(verteilung), "Dario"))
    ergebnis = e.spielen()
    assert "Die Werwölfe sind: Ben. Sie kennen dich nicht." in e.spieler["Anna"].wissen
    assert "Freimaurer sind außer dir: Dario." in e.spieler["Clara"].wissen
    assert not any("Anna" in w for w in e.spieler["Ben"].wissen)  # Werwolf kennt den Günstling nicht
    # Clara (Freimaurer) stirbt, kein Werwolf: Rudel (Ben + Günstling Anna) gewinnt.
    assert ergebnis.gewinner == {Partei.WERWOELFE} and set(ergebnis.sieger) == {"Anna", "Ben"}


def test_abstimmung_ist_gleichzeitig() -> None:
    verteilung = {"Anna": R.WERWOLF, "Ben": R.DORFBEWOHNER, "Clara": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Anna", list(verteilung), "Ben")
    engine(verteilung, [R.SEHERIN, R.RAEUBER, R.UNRUHESTIFTERIN], agenten).spielen()
    for agent in agenten.values():
        abstimm_zug = next(z for z in agent.zuege if z.erlaubte_tools == [ABSTIMMEN])
        assert not any(e.art == "stimme" for e in abstimm_zug.ereignisse)


# Doppelgängerin: Sie ahmt die Rolle nach, die sie ansieht, und wechselt die Partei.

def test_doppelgaengerin_wird_werwolf() -> None:
    verteilung = {"Anna": R.DOPPELGAENGERIN, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Ben")
    agenten["Anna"].nacht = Aktion(NACHAHMEN, {"ziel": "Ben"})
    e = engine(verteilung, [R.SEHERIN, R.RAEUBER, R.UNRUHESTIFTERIN], agenten)
    ergebnis = e.spielen()

    assert e.kopie is R.WERWOLF
    assert "Die Werwölfe sind: Ben, Anna." in e.spieler["Ben"].wissen  # wacht mit den Werwölfen auf
    assert ergebnis.gewinner == {Partei.WERWOELFE} and set(ergebnis.sieger) == {"Anna", "Ben"}


def test_doppelgaengerin_als_seherin_handelt_sofort() -> None:
    verteilung = {"Anna": R.DOPPELGAENGERIN, "Ben": R.SEHERIN, "Clara": R.WERWOLF}

    class DoppelSeherin(Skript):
        def handeln(self, zug: Zug) -> Aktion:
            self.zuege.append(zug)
            if NACHAHMEN in zug.erlaubte_tools:
                return Aktion(NACHAHMEN, {"ziel": "Ben"})
            if SPIELER_ANSEHEN in zug.erlaubte_tools:
                return Aktion(SPIELER_ANSEHEN, {"ziel": "Clara"})
            return super().handeln(zug)

    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Ben")
    agenten["Anna"] = DoppelSeherin(stimme="Clara")
    e = engine(verteilung, [R.DORFBEWOHNER, R.RAEUBER, R.UNRUHESTIFTERIN], agenten)
    e.spielen()
    assert "Du hast die Karte von Clara angesehen: Werwolf." in e.spieler["Anna"].wissen
    # Die Seherin-Aktion kam direkt nach dem Nachahmen, vor den Werwölfen.
    nacht = [x.daten.get("aktion") for x in e.protokoll if x.art == "nacht_aktion"]
    assert nacht[:2] == [NACHAHMEN, SPIELER_ANSEHEN]


def test_doppelgaengerin_als_schlaflose_wacht_zuletzt() -> None:
    verteilung = {"Anna": R.DOPPELGAENGERIN, "Ben": R.SCHLAFLOSE, "Clara": R.WERWOLF}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Ben")
    agenten["Anna"].nacht = Aktion(NACHAHMEN, {"ziel": "Ben"})
    e = engine(verteilung, [R.DORFBEWOHNER, R.RAEUBER, R.UNRUHESTIFTERIN], agenten)
    e.spielen()
    assert e.spieler["Anna"].wissen[-1] == "Am Ende der Nacht liegt diese Karte vor dir: Doppelgängerin."


def test_wer_die_doppelgaengerin_karte_bekommt_uebernimmt_die_kopie() -> None:
    # Anna ahmt den Werwolf nach, der Räuber Dario raubt danach Annas Karte.
    verteilung = {"Anna": R.DOPPELGAENGERIN, "Ben": R.WERWOLF, "Clara": R.DORFBEWOHNER, "Dario": R.RAEUBER}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Ben")
    agenten["Anna"].nacht = Aktion(NACHAHMEN, {"ziel": "Ben"})
    agenten["Dario"].nacht = Aktion(RAUBEN, {"ziel": "Anna"})
    e = engine(verteilung, [R.SEHERIN, R.SEHERIN, R.UNRUHESTIFTERIN], agenten)
    ergebnis = e.spielen()

    assert ergebnis.endrollen["Dario"] is R.WERWOLF  # Doppelgängerin-Karte = Werwolf
    assert ergebnis.endrollen["Anna"] is R.RAEUBER
    assert set(ergebnis.sieger) == {"Ben", "Dario"}


def test_nachtreihenfolge_wird_allen_angesagt() -> None:
    verteilung = {"Anna": R.UNRUHESTIFTERIN, "Ben": R.WERWOLF, "Clara": R.RAEUBER}
    agenten = {n: Skript() for n in verteilung}
    ereignisse = []
    karten = list(verteilung.values()) + [R.DORFBEWOHNER, R.SCHLAFLOSE, R.SEHERIN]
    VollmondEngine(agenten, karten, rng=random.Random(0), verteilung=verteilung,
                   mitte=[R.DORFBEWOHNER, R.SCHLAFLOSE, R.SEHERIN], beobachter=ereignisse.append).spielen()
    ansage = next(e for e in ereignisse if e.art == "karten")
    assert ansage.oeffentlich
    # Nur Rollen mit Nachtaktion, die im Spiel sind – auch die aus der Mitte.
    assert ansage.daten["reihenfolge"] == "Werwolf, Seherin, Räuber, Unruhestifterin, Schlaflose"
    assert "Reihenfolge dran: Werwolf, Seherin" in ansage.text


def test_raeuber_erfaehrt_was_nach_ihm_noch_passieren_kann() -> None:
    # Wie Serie 6, Partie 1: Der Räuber raubt die Unruhestifterin, die danach noch tauscht.
    verteilung = {"Anna": R.RAEUBER, "Ben": R.UNRUHESTIFTERIN, "Clara": R.WERWOLF, "Dario": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Anna")
    agenten["Anna"].nacht = Aktion(RAUBEN, {"ziel": "Ben"})
    agenten["Ben"].nacht = Aktion(VERTAUSCHEN, {"ziel1": "Anna", "ziel2": "Clara"})
    e = engine(verteilung, [R.SEHERIN, R.SCHLAFLOSE, R.DORFBEWOHNER], agenten)
    e.spielen()

    wissen = " ".join(e.spieler["Anna"].wissen)
    assert "Nach dir waren noch dran: Unruhestifterin, Schlaflose." in wissen
    assert "Ben ist trotzdem noch als Unruhestifterin aufgewacht" in wissen
    # Und tatsächlich: Ben hat danach Anna vertauscht, Anna hat jetzt die Werwolf-Karte.
    assert e.karten["Anna"] is R.WERWOLF


def test_raeuber_ohne_spaetere_rollen_bekommt_keinen_zusatz() -> None:
    verteilung = {"Anna": R.RAEUBER, "Ben": R.DORFBEWOHNER, "Clara": R.WERWOLF}
    agenten = alle_stimmen_fuer("Clara", list(verteilung), "Anna")
    agenten["Anna"].nacht = Aktion(RAUBEN, {"ziel": "Ben"})
    e = engine(verteilung, [R.SEHERIN, R.DORFBEWOHNER, R.DORFBEWOHNER], agenten)
    e.spielen()
    assert not any("Nach dir" in w for w in e.spieler["Anna"].wissen)


def test_einsamer_wolf_weiss_welche_rolle_niemand_hat() -> None:
    # Jede Mittelkarte kommt nur einmal vor: Was der Wolf sieht, hatte niemand am Tisch.
    verteilung = {"Anna": R.WERWOLF, "Ben": R.DORFBEWOHNER, "Clara": R.DORFBEWOHNER}
    agenten = alle_stimmen_fuer("Ben", list(verteilung), "Clara")
    e = engine(verteilung, [R.RAEUBER, R.SEHERIN, R.UNRUHESTIFTERIN], agenten)
    e.spielen()
    wissen = next(w for w in e.spieler["Anna"].wissen if w.startswith("Du bist der einzige Werwolf"))
    assert "Also hatte kein Mitspieler zu Beginn die Karte" in wissen


def test_einsamer_wolf_folgert_nichts_bei_mehrfachen_karten() -> None:
    # Dorfbewohner gibt es mehrfach – daraus folgt nichts über die Mitspieler.
    verteilung = {"Anna": R.WERWOLF, "Ben": R.DORFBEWOHNER, "Clara": R.SEHERIN}
    agenten = alle_stimmen_fuer("Ben", list(verteilung), "Clara")
    e = engine(verteilung, [R.DORFBEWOHNER, R.DORFBEWOHNER, R.WERWOLF], agenten)
    e.spielen()
    wissen = next(w for w in e.spieler["Anna"].wissen if w.startswith("Du bist der einzige Werwolf"))
    assert "kein Mitspieler" not in wissen
