import random

from werwolf.engine import Engine
from werwolf.mock_agent import MockAgent
from werwolf.protokoll import Protokoll
from werwolf.schnittstelle import Ereignis, Phase


def test_ueberschriften_und_geheim_markierung() -> None:
    protokoll = Protokoll(ausgabe=None)
    protokoll(Ereignis(1, Phase.NACHT, "Es wird Nacht."))
    protokoll(Ereignis(1, Phase.NACHT, "Anna (Werwolf) wählt Ben.", oeffentlich=False))
    protokoll(Ereignis(1, Phase.MORGEN, "Ben ist tot."))
    protokoll(Ereignis(2, Phase.NACHT, "Es wird Nacht."))

    assert protokoll.zeilen == [
        "",
        "=== Runde 1 ===",
        "--- Nacht ---",
        "Es wird Nacht.",
        "    [geheim] Anna (Werwolf) wählt Ben.",
        "--- Morgen ---",
        "Ben ist tot.",
        "",
        "=== Runde 2 ===",
        "--- Nacht ---",
        "Es wird Nacht.",
    ]


def test_ganze_partie_wird_gespeichert(tmp_path) -> None:
    protokoll = Protokoll(ausgabe=None)
    namen = ["Anna", "Ben", "Clara", "Dario", "Emil"]
    engine = Engine({n: MockAgent(random.Random(i)) for i, n in enumerate(namen)},
                    rng=random.Random(0), beobachter=protokoll)
    protokoll.kopf("Testpartie", [f"{s.name}: {s.rolle.value}" for s in engine.spieler.values()])
    engine.spielen()

    pfad = tmp_path / "logs" / "partie.txt"
    protokoll.speichern(pfad)
    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("Testpartie\n==========\n- Anna: ")
    assert "=== Runde 1 ===" in text
    assert "--- Spielende ---\nSpielende:" in text
