"""Ein Agent, der zufällig handelt. Kostet nichts und testet die Engine."""

import random

from werwolf.schnittstelle import ZIEL_TOOLS, Aktion, Zug

SAETZE = [
    "Ich traue {name} nicht.",
    "{name} war gestern auffällig still.",
    "Ich bin ganz sicher kein Werwolf.",
    "Lasst uns nichts überstürzen.",
    "Was sagt ihr zu {name}?",
]


class MockAgent:
    """Wählt zufällige Ziele unter allen anderen Lebenden.

    Absichtlich etwas dumm: Ein Werwolf kann z. B. seinen Mitwolf als Opfer
    vorschlagen. Die Engine lehnt das ab – so wird die Validierung gleich mitgetestet.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def handeln(self, zug: Zug) -> Aktion:
        # Nur bei echter Wahl würfeln, damit alte Partien mit gleichem Seed gleich bleiben.
        tool = zug.erlaubte_tools[0]
        if len(zug.erlaubte_tools) > 1:
            tool = self.rng.choice(zug.erlaubte_tools)
        if tool in zug.optionen:
            # Jeden Parameter unabhängig würfeln. Das kann ungültig sein (z. B. zweimal
            # dasselbe Ziel) – auch das testet die Validierung der Engine.
            parameter = {name: self.rng.choice(werte) for name, werte in zug.optionen[tool].items()}
            return Aktion(tool, parameter)
        andere = [name for name in zug.lebende if name != zug.ich]
        if tool in ZIEL_TOOLS:
            return Aktion(tool, {"ziel": self.rng.choice(andere), "begruendung": "Zufall"})
        satz = self.rng.choice(SAETZE).format(name=self.rng.choice(andere))
        return Aktion(tool, {"text": satz})
