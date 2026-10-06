"""Vollmondnacht mit LLM-Spielern – mit Fake-Client, kostenlos und ohne Internet."""

import random

from core.llm_client import Antwort
from core.tools import ToolCall, ToolSchema
from werwolf.vollmondnacht.engine import NACHAHMEN, NICHTS_TUN, VERTAUSCHEN, VollmondEngine
from werwolf.vollmondnacht.llm_spieler import ROLLEN_HINWEISE, VollmondLLMSpieler
from werwolf.vollmondnacht.rollen import Rolle, szenario_karten

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta", "Hugo"]


class FakeClient:
    """Wählt immer das erste Tool und für jeden Parameter den ersten erlaubten Wert."""

    def __init__(self) -> None:
        self.anfragen_liste: list[tuple[str, str, list[ToolSchema]]] = []

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        self.anfragen_liste.append((system, nachricht, tools))
        tool = tools[0]
        argumente = {}
        for name, schema in tool.parameter.items():
            if "enum" in schema:
                # Bei zwei Zielen verschiedene Werte nehmen.
                argumente[name] = schema["enum"][len(argumente) % len(schema["enum"])]
            elif name in tool.pflicht:
                argumente[name] = "Ich bin ein harmloser Dorfbewohner."
        return Antwort(ToolCall(tool.name, argumente))


def test_jede_rolle_hat_einen_hinweis() -> None:
    assert set(ROLLEN_HINWEISE) == set(Rolle)


def test_ganze_partie_nur_mit_llm_spielern_ohne_zufallsaktionen() -> None:
    # „Wiedergänger“ enthält fast alle Rollen, auch die Doppelgängerin.
    client = FakeClient()
    karten = szenario_karten("Wiedergänger", 8, random.Random(1))
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in NAMEN}
    e = VollmondEngine(agenten, karten, rng=random.Random(1))
    e.spielen()

    assert not any(x.art in ("zufallsaktion", "ungueltig") for x in e.protokoll)
    tools = {t.name for _, _, ts in client.anfragen_liste for t in ts}
    assert {"sprechen", "abstimmen"} <= tools


def test_prompts_und_tools() -> None:
    client = FakeClient()
    verteilung = {"Anna": Rolle.UNRUHESTIFTERIN, "Ben": Rolle.WERWOLF, "Clara": Rolle.DORFBEWOHNER}
    agenten = {n: VollmondLLMSpieler(client, "frech") for n in verteilung}
    mitte = [Rolle.SEHERIN, Rolle.RAEUBER, Rolle.DOPPELGAENGERIN]
    e = VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                       verteilung=verteilung, mitte=mitte)
    e.spielen()

    system, nachricht, tools = client.anfragen_liste[0]  # Nacht der Unruhestifterin
    assert "Du bist Anna" in system and "Unruhestifterin" in system and "frech" in system
    assert "Im Spiel sind diese 6 Karten" in nachricht
    assert [t.name for t in tools] == [VERTAUSCHEN, NICHTS_TUN]
    assert sorted(tools[0].parameter["ziel1"]["enum"]) == ["Ben", "Clara"]
    # Gleiche (gemischte) Reihenfolge für beide Ziele.
    assert tools[0].parameter["ziel1"]["enum"] == tools[0].parameter["ziel2"]["enum"]
    assert tools[1].parameter == {}
    # Die Doppelgängerin liegt in der Mitte, also fragt die Engine nie nach „nachahmen“.
    assert not any(NACHAHMEN in [t.name for t in ts] for _, _, ts in client.anfragen_liste)


def test_nur_werwoelfe_und_gerber_duerfen_luegen() -> None:
    from werwolf.vollmondnacht.llm_spieler import EHRLICH, KARTENWEG, LUEGEN, rollen_hinweis

    for rolle in Rolle:
        hinweis = rollen_hinweis(rolle)
        if rolle in (Rolle.WERWOLF, Rolle.GUENSTLING, Rolle.GERBER):
            assert LUEGEN in hinweis and EHRLICH not in hinweis, rolle
            assert KARTENWEG not in hinweis, rolle  # nur das Dorf bekommt den Hinweis
        elif rolle is Rolle.DOPPELGAENGERIN:
            assert "darfst du lügen" in hinweis  # hängt von der Kopie ab
        else:
            assert EHRLICH in hinweis and LUEGEN not in hinweis, rolle
            assert KARTENWEG in hinweis, rolle
    # Der Räuber kann nachts zum Werwolf werden und darf dann lügen.
    assert "darfst lügen" in rollen_hinweis(Rolle.RAEUBER)


def test_wer_nachts_werwolf_wird_wechselt_die_seite() -> None:
    from werwolf.vollmondnacht.llm_spieler import EHRLICH, LUEGEN, rollen_hinweis

    # Schlaflose sieht morgens eine Werwolf-Karte: jetzt Rudel, also kein Ehrlichkeits-Hinweis.
    hinweis = rollen_hinweis(Rolle.SCHLAFLOSE, Rolle.WERWOLF)
    assert "Werwolfsrudel" in hinweis and LUEGEN in hinweis and EHRLICH not in hinweis
    # Räuber raubt eine Dorfkarte: bleibt Dorf, bleibt ehrlich.
    assert rollen_hinweis(Rolle.RAEUBER, Rolle.SEHERIN) == rollen_hinweis(Rolle.RAEUBER)


def test_system_prompt_erlaubt_luegen_nicht_mehr_allen() -> None:
    client = FakeClient()
    verteilung = {"Anna": Rolle.SEHERIN, "Ben": Rolle.WERWOLF, "Clara": Rolle.DORFBEWOHNER}
    mitte = [Rolle.DORFBEWOHNER, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    seherin_system = client.anfragen_liste[0][0]  # erste Anfrage: Nacht der Seherin
    assert "Du darfst alles behaupten und lügen" not in seherin_system
    assert "Das Dorf gewinnt durch Ehrlichkeit" in seherin_system


def test_system_prompt_erklaert_alle_rollen_der_partie() -> None:
    # Ohne diese Liste behaupteten Werwölfe z. B. „Seherin, eine Mittelkarte angesehen“ –
    # die Seherin sieht aber eine Spielerkarte oder ZWEI Mittelkarten.
    client = FakeClient()
    verteilung = {"Anna": Rolle.WERWOLF, "Ben": Rolle.DORFBEWOHNER, "Clara": Rolle.SCHLAFLOSE}
    mitte = [Rolle.SEHERIN, Rolle.RAEUBER, Rolle.DORFBEWOHNER]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    system = client.anfragen_liste[0][0]
    assert "Rollen in dieser Partie" in system
    assert "- Seherin: sieht entweder die Karte eines Mitspielers oder zwei Karten aus der Mitte" in system
    assert "- Räuber:" in system  # liegt in der Mitte, ist aber im Spiel
    assert "- Jäger:" not in system and "- Doppelgängerin:" not in system  # nicht in dieser Partie
    # In der Reihenfolge der Nacht
    assert system.index("- Werwolf:") < system.index("- Seherin:") < system.index("- Schlaflose:")


def test_erste_wortmeldung_verlangt_die_startkarte() -> None:
    from werwolf.vollmondnacht.llm_spieler import ERSTE_REDE

    client = FakeClient()
    verteilung = {"Anna": Rolle.WERWOLF, "Ben": Rolle.DORFBEWOHNER, "Clara": Rolle.SCHLAFLOSE}
    mitte = [Rolle.SEHERIN, Rolle.RAEUBER, Rolle.DORFBEWOHNER]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    reden = [nachricht for _, nachricht, tools in client.anfragen_liste if tools[0].name == "sprechen"]
    # 3 Spieler × 2 Diskussionsrunden: nur die ersten drei Reden verlangen die Startkarte.
    assert [ERSTE_REDE.strip() in r for r in reden] == [True, True, True, False, False, False]
    # Vage Behauptungen („zwei Mittelkarten angesehen“) reichen nicht: Die Karten müssen genannt werden.
    assert "welche Mittelkarten" in ERSTE_REDE


def test_tauscher_sprechen_die_folge_ihres_tauschs_aus() -> None:
    from werwolf.vollmondnacht.llm_spieler import TAUSCH_FOLGE

    client = FakeClient()
    verteilung = {"Anna": Rolle.UNRUHESTIFTERIN, "Ben": Rolle.RAEUBER, "Clara": Rolle.WERWOLF}
    mitte = [Rolle.SEHERIN, Rolle.DORFBEWOHNER, Rolle.SCHLAFLOSE]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    # Nur die erste Rede der beiden Tauscher, nicht die des Werwolfs und nicht später.
    mit_folge = [
        name for system, nachricht, tools in client.anfragen_liste
        if tools[0].name == "sprechen" and TAUSCH_FOLGE.strip() in nachricht
        for name in verteilung if f"Du bist {name}" in system
    ]
    assert mit_folge == ["Anna", "Ben"]
