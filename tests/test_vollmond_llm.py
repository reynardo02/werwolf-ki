"""Vollmondnacht mit LLM-Spielern – mit Fake-Client, kostenlos und ohne Internet."""

import random
from dataclasses import replace

from core.llm_client import Antwort
from core.tools import ToolCall, ToolSchema
from werwolf.schnittstelle import ABSTIMMEN, SPRECHEN, Ereignis, Phase, Zug
from werwolf.vollmondnacht.engine import NACHAHMEN, VERTAUSCHEN, VollmondEngine
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
    assert [t.name for t in tools] == [VERTAUSCHEN]  # kein „nichts tun“ (Partie 696964)
    assert sorted(tools[0].parameter["ziel1"]["enum"]) == ["Ben", "Clara"]
    # Gleiche (gemischte) Reihenfolge für beide Ziele.
    assert tools[0].parameter["ziel1"]["enum"] == tools[0].parameter["ziel2"]["enum"]
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


def test_kartenweg_schuetzt_dorf_karten_und_nennt_den_betrunkenen() -> None:
    # Serie 15, Seed 920520: Das Dorf tötete eine Spielerin, der es selbst eine Dorf-Karte zurechnete.
    from werwolf.vollmondnacht.llm_spieler import KARTENWEG

    assert "am Ende eine Dorf-Karte hat, ist kein Werwolf" in KARTENWEG
    assert "Betrunkene eine Mittelkarte genommen" in KARTENWEG


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
    # Der Werwolf liegt in der Mitte, damit der Räuber sicher Dorf bleibt.
    verteilung = {"Anna": Rolle.UNRUHESTIFTERIN, "Ben": Rolle.RAEUBER, "Clara": Rolle.DORFBEWOHNER}
    mitte = [Rolle.SEHERIN, Rolle.WERWOLF, Rolle.SCHLAFLOSE]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    # Nur die erste Rede der beiden Tauscher, nicht die des Dorfbewohners und nicht später.
    mit_folge = [
        name for system, nachricht, tools in client.anfragen_liste
        if tools[0].name == "sprechen" and TAUSCH_FOLGE.strip() in nachricht
        for name in verteilung if f"Du bist {name}" in system
    ]
    assert mit_folge == ["Anna", "Ben"]


def test_raeuber_mit_werwolf_karte_verraet_sich_nicht() -> None:
    from werwolf.vollmondnacht.llm_spieler import ERSTE_REDE, TAUSCH_FOLGE

    spieler = VollmondLLMSpieler(FakeClient(), "ruhig")
    zug = Zug(ich="Ben", rolle=Rolle.RAEUBER, runde=1, phase=Phase.DISKUSSION,
              erlaubte_tools=[SPRECHEN], lebende=["Anna", "Ben"], geheimwissen=[], notizen=[],
              ereignisse=[], bekannte_karte=Rolle.WERWOLF)
    nachricht = spieler.zug_prompt(zug)
    assert ERSTE_REDE in nachricht and TAUSCH_FOLGE not in nachricht
    assert "Darfst du lügen" in ERSTE_REDE
    assert TAUSCH_FOLGE in spieler.zug_prompt(replace(zug, bekannte_karte=Rolle.DORFBEWOHNER))


def test_wer_nachts_werwolf_wird_soll_es_nicht_verraten() -> None:
    # Serie 12/13: Schlaflose und Räuber mit Werwolf-Karte sagten „jetzt bin ich Werwolf“.
    from werwolf.vollmondnacht.llm_spieler import NICHT_VERRATEN

    spieler = VollmondLLMSpieler(FakeClient(), "ruhig")
    warnung = NICHT_VERRATEN.format(karte="Werwolf")
    zug = Zug(ich="Ben", rolle=Rolle.SCHLAFLOSE, runde=1, phase=Phase.DISKUSSION,
              erlaubte_tools=[SPRECHEN], lebende=["Anna", "Ben"], geheimwissen=[], notizen=[],
              ereignisse=[], bekannte_karte=Rolle.WERWOLF)
    assert warnung in spieler.zug_prompt(zug)
    # Auch in späteren Reden, aber nicht für Spieler, die beim Dorf geblieben sind.
    rede = Ereignis(1, Phase.DISKUSSION, 'Ben: "Hallo."', art="rede", daten={"spieler": "Ben"})
    assert warnung in spieler.zug_prompt(replace(zug, ereignisse=[rede]))
    assert "Verrate das auf keinen Fall" not in spieler.zug_prompt(
        replace(zug, bekannte_karte=Rolle.SCHLAFLOSE))
    assert "Verrate das auf keinen Fall" not in spieler.zug_prompt(
        replace(zug, rolle=Rolle.WERWOLF, bekannte_karte=None))


def test_regeln_sagen_dass_nur_die_startkarte_handelt() -> None:
    # Eigene Partie 667996: Das Dorf meinte, wer die Schlaflose-Karte erst nachts bekommt,
    # hätte am Ende etwas sehen müssen – und hielt die ehrliche Unruhestifterin für eine Lügnerin.
    client = FakeClient()
    verteilung = {"Anna": Rolle.UNRUHESTIFTERIN, "Ben": Rolle.WERWOLF, "Clara": Rolle.DORFBEWOHNER}
    mitte = [Rolle.SEHERIN, Rolle.SCHLAFLOSE, Rolle.DORFBEWOHNER]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    for system, _, _ in client.anfragen_liste:
        assert "Nachts handelt jeder nur mit seiner Startkarte" in system


def test_regeln_erklaeren_die_nachtreihenfolge() -> None:
    # Eigene Partie 583495: Das Dorf meinte, die Seherin hätte bei Ben schon die Räuber-Karte
    # sehen müssen – dabei ist die Seherin vor dem Räuber dran.
    client = FakeClient()
    verteilung = {"Anna": Rolle.RAEUBER, "Ben": Rolle.WERWOLF, "Clara": Rolle.SEHERIN}
    mitte = [Rolle.DORFBEWOHNER, Rolle.SCHLAFLOSE, Rolle.DORFBEWOHNER]
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in verteilung}
    VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                   verteilung=verteilung, mitte=mitte).spielen()
    for system, _, _ in client.anfragen_liste:
        assert "in der Reihenfolge, in der sie nachts\naufwachen" in system
        assert "sieht sie so, wie sie in diesem Moment ist" in system
        # Die Rollenliste steht wirklich in Nachtreihenfolge.
        assert system.index("- Werwolf:") < system.index("- Seherin:") < system.index("- Räuber:")


def test_werwolf_soll_die_gesehene_mittelkarte_behaupten() -> None:
    # Eigene Partie 522974: Der Wolf sah die Seherin in der Mitte und behauptete trotzdem Schlaflose.
    hinweis = ROLLEN_HINWEISE[Rolle.WERWOLF]
    assert "Mittelkarte angesehen" in hinweis
    # Serie 11, Partie 3: Mit Beispiel statt „auch die Seherin“, das auf die Seherin lenkte.
    assert "Betrunkener gesehen → behaupte Betrunkener" in hinweis
    # Serie 12: Wölfe verrieten die gesehene Mittelkarte und damit sich selbst.
    assert "Erwähne aber nie, dass oder welche Mittelkarte du gesehen hast" in hinweis


def test_eigene_reden_und_stimmen_sind_als_du_markiert() -> None:
    # Serie 11: Ben sagte „ich vote Ben“, Anna redete von sich in der dritten Person.
    from werwolf.schnittstelle import Ereignis

    ereignisse = [
        Ereignis(1, Phase.DISKUSSION, 'Ben: "Ich war Räuber."', art="rede", daten={"spieler": "Ben"}),
        Ereignis(1, Phase.DISKUSSION, 'Anna: "Ben lügt."', art="rede", daten={"spieler": "Anna"}),
        Ereignis(1, Phase.DISKUSSION, "Ben zeigt auf Anna.", art="stimme",
                 daten={"von": "Ben", "ziel": "Anna"}),
        Ereignis(1, Phase.DISKUSSION, "Anna zeigt auf Ben.", art="stimme",
                 daten={"von": "Anna", "ziel": "Ben"}),
    ]
    zug = Zug(ich="Ben", rolle=Rolle.RAEUBER, runde=1, phase=Phase.DISKUSSION,
              erlaubte_tools=[SPRECHEN], lebende=["Anna", "Ben"], geheimwissen=[], notizen=[],
              ereignisse=ereignisse)
    nachricht = VollmondLLMSpieler(FakeClient(), "ruhig").zug_prompt(zug)
    assert 'Ben (du): "Ich war Räuber."' in nachricht
    assert "Ben (du) zeigt auf Anna." in nachricht
    assert 'Anna: "Ben lügt."' in nachricht and "Anna zeigt auf Ben." in nachricht


def test_dorf_stimmt_nicht_gegen_eine_dorf_karte() -> None:
    # Serie 15, Seeds 920520/920529: Das Dorf tötete Spieler, denen es selbst eine Dorf-Karte zurechnete.
    from werwolf.vollmondnacht.llm_spieler import DORF_STIMME

    spieler = VollmondLLMSpieler(FakeClient(), "ruhig")
    zug = Zug(ich="Anna", rolle=Rolle.DORFBEWOHNER, runde=1, phase=Phase.ABSTIMMUNG,
              erlaubte_tools=[ABSTIMMEN], lebende=["Anna", "Ben"], geheimwissen=[], notizen=[],
              ereignisse=[])
    assert DORF_STIMME in spieler.zug_prompt(zug)
    assert DORF_STIMME not in spieler.zug_prompt(replace(zug, rolle=Rolle.WERWOLF))
    # Wer nachts eine Werwolf-Karte geraubt hat, stimmt fürs Rudel.
    assert DORF_STIMME not in spieler.zug_prompt(
        replace(zug, rolle=Rolle.RAEUBER, bekannte_karte=Rolle.WERWOLF))


def test_regeln_beraubte_nennen_zu_recht_ihre_startkarte() -> None:
    from pathlib import Path

    system = (Path(__file__).parent.parent / "werwolf/vollmondnacht/prompts/system.txt").read_text(encoding="utf-8")
    assert "nennt zu Recht seine Startkarte" in system
    assert "bestätigt diese Startkarte" in system
    assert "Schlaflose, die vorher vertauscht\n  wurde, sieht am Ende die Karte" in system
