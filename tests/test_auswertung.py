from pathlib import Path

import pytest

from main import partie_spielen
from werwolf.auswertung import auswerten, bericht, partie_aus_log
from werwolf.jsonl_log import log_lesen


def ereignis(art: str, runde: int = 1, **daten: str) -> dict:
    return {"art": art, "runde": runde, "phase": "x", "oeffentlich": True, "text": "", "daten": daten}


def kopf(modell: str | None = None, typ: str = "mock") -> dict:
    rollen = {"Anna": "Werwolf", "Ben": "Seherin", "Clara": "Dorfbewohner",
              "Dario": "Dorfbewohner", "Emil": "Dorfbewohner"}
    return {"art": "partie", "modell": modell, "seed": 1,
            "spieler": [{"name": n, "rolle": r, "typ": typ} for n, r in rollen.items()]}


# Kleine Partie zum Nachrechnen: Ben (Seherin) findet Anna (Werwolf),
# stimmt gegen sie, das Dorf richtet Anna hin.
LOG = [
    kopf(),
    ereignis("pruefung", seherin="Ben", ziel="Anna", rolle="Werwolf"),
    ereignis("tod", name="Clara", rolle="Dorfbewohner", ursache="nacht"),
    ereignis("stimme", von="Anna", ziel="Ben"),
    ereignis("stimme", von="Ben", ziel="Anna"),
    ereignis("stimme", von="Dario", ziel="Anna"),
    ereignis("stimme", von="Emil", ziel="Dario"),
    ereignis("tod", name="Anna", rolle="Werwolf", ursache="abstimmung"),
    ereignis("spielende", gewinner="Dorf"),
    {"art": "ergebnis", "gewinner": "Dorf", "runden": 1, "api": None},
]


def test_zaehlt_eine_partie_richtig() -> None:
    a = auswerten([partie_aus_log(LOG)])
    assert a.partien == 1 and a.siege_werwoelfe == 0 and a.runden == 1
    assert (a.pruefungen, a.pruefungen_werwolf) == (1, 1)
    assert (a.seherin_gelegenheiten, a.seherin_wissen_genutzt) == (1, 1)
    assert a.seherin_tot_in_nacht_1 == 0
    # Dorf-Stimmen: Ben, Dario, Emil (Annas Stimme zählt nicht), zwei davon gegen Anna.
    assert (a.dorf_stimmen, a.dorf_stimmen_werwolf) == (3, 2)
    # 4 Lebende, 1 Wolf: Zufall trifft ihn mit 1/3, bei drei Stimmen also 1.0 erwartet.
    assert a.dorf_stimmen_erwartet_zufall == pytest.approx(1.0)
    assert (a.hinrichtungen, a.hinrichtungen_werwolf) == (1, 1)


def test_abgebrochene_partie_zaehlt_nicht_in_siegquote() -> None:
    abbruch = [kopf("m", "llm"), {"art": "abbruch", "grund": "Budget", "api": {"aufrufe": 400, "fehler": 2}}]
    a = auswerten([partie_aus_log(LOG), partie_aus_log(abbruch)])
    assert (a.partien, a.abgebrochen, a.fertige) == (2, 1, 1)
    assert a.api_aufrufe == 400 and a.api_fehler == 2
    assert set(a.gruppen) == {"nur MockAgenten", "m (5/5 Spieler LLM)"}
    assert "davon 1 abgebrochen" in bericht(a)


def test_ungueltiges_log() -> None:
    with pytest.raises(ValueError):
        partie_aus_log([{"art": "stimme"}])


def test_zwanzig_partien_auswerten(tmp_path: Path) -> None:
    """Meilenstein-4-Kriterium: 20 Partien spielen, loggen und auswerten."""
    for i in range(20):
        partie_spielen(100 + i, 7, 0, None, f"partie_{i:03d}", ausfuehrlich=False, ordner=tmp_path)

    logs = sorted(tmp_path.glob("*.jsonl"))
    assert len(logs) == 20 and len(list(tmp_path.glob("*.txt"))) == 20
    a = auswerten([partie_aus_log(log_lesen(p)) for p in logs])

    assert a.partien == 20 and a.abgebrochen == 0
    assert 0 <= a.siege_werwoelfe <= 20
    assert a.dorf_stimmen > 0 and a.pruefungen > 0
    text = bericht(a, "Test")
    assert "Siegquote Werwölfe" in text and "Zufall wäre" in text


def test_abbruch_wird_geloggt_und_weitergereicht(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tageslimit oder Strg+C: Partie als 'abbruch' loggen, dann die Serie stoppen."""
    import main
    from core.llm_client import KontingentErschoepft
    from werwolf.engine import Engine

    def gesperrt(self: Engine) -> None:
        raise KontingentErschoepft("PerDay")

    monkeypatch.setattr(Engine, "spielen", gesperrt)
    with pytest.raises(KontingentErschoepft):
        main.partie_spielen(1, 7, 0, None, "partie", ausfuehrlich=False, ordner=tmp_path)

    zeilen = log_lesen(tmp_path / "partie.jsonl")
    assert zeilen[-1]["art"] == "abbruch"
    assert "Partie abgebrochen" in (tmp_path / "partie.txt").read_text(encoding="utf-8")
    assert partie_aus_log(zeilen).gewinner is None  # zählt in der Auswertung als abgebrochen
