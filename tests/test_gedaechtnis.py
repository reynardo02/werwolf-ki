from core.gedaechtnis import Erinnerung, kontext_auswaehlen

ERINNERUNGEN = [
    Erinnerung(1, "Anna redet viel."),
    Erinnerung(1, "Ben ist gestorben.", wichtig=True),
    Erinnerung(2, "Clara verdächtigt Emil."),
    Erinnerung(3, "Dario schweigt."),
]


def test_nur_aktuelle_runde_plus_wichtiges() -> None:
    texte = [e.text for e in kontext_auswaehlen(ERINNERUNGEN, aktuelle_runde=3)]
    assert texte == ["Ben ist gestorben.", "Dario schweigt."]


def test_groesseres_fenster() -> None:
    texte = [e.text for e in kontext_auswaehlen(ERINNERUNGEN, aktuelle_runde=3, volle_runden=2)]
    assert texte == ["Ben ist gestorben.", "Clara verdächtigt Emil.", "Dario schweigt."]


def test_erste_runde_sieht_alles() -> None:
    assert kontext_auswaehlen(ERINNERUNGEN[:2], aktuelle_runde=1) == ERINNERUNGEN[:2]
