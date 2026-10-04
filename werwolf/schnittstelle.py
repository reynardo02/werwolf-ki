"""Die Schnittstelle zwischen Engine und Agenten.

Die Engine fragt einen Agenten mit einem `Zug` (was er sehen darf und welche
Tools gerade erlaubt sind) und bekommt eine `Aktion` zurück. Eine Aktion ist
absichtlich wie ein Tool-Call aufgebaut (Name + Parameter), damit in M2 ein
LLM-Agent dieselbe Schnittstelle bedienen kann wie der MockAgent.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from werwolf.roles import Rolle


class Phase(Enum):
    NACHT = "Nacht"
    MORGEN = "Morgen"
    DISKUSSION = "Diskussion"
    ABSTIMMUNG = "Abstimmung"
    RUNDENENDE = "Rundenende"


# Namen der Tools, wie sie später auch das LLM sieht.
SPRECHEN = "sprechen"
ABSTIMMEN = "abstimmen"
OPFER_WAEHLEN = "opfer_waehlen"
PRUEFEN = "pruefen"
NOTIZ_SCHREIBEN = "notiz_schreiben"

# Tools mit einem Ziel-Spieler bzw. mit einem Freitext.
ZIEL_TOOLS = {ABSTIMMEN, OPFER_WAEHLEN, PRUEFEN}
TEXT_TOOLS = {SPRECHEN, NOTIZ_SCHREIBEN}


@dataclass(frozen=True)
class Ereignis:
    """Ein Eintrag im Spielprotokoll."""

    runde: int
    phase: Phase
    text: str
    oeffentlich: bool = True  # False: nur im Protokoll, kein Agent sieht es


@dataclass
class Aktion:
    """Antwort eines Agenten, aufgebaut wie ein Tool-Call."""

    tool: str
    parameter: dict[str, str] = field(default_factory=dict)


@dataclass
class Zug:
    """Alles, was ein Agent für seine Entscheidung sehen darf."""

    ich: str
    rolle: Rolle
    runde: int
    phase: Phase
    erlaubte_tools: list[str]
    lebende: list[str]
    geheimwissen: list[str]
    notizen: list[str]
    ereignisse: list[Ereignis]
    hinweis: str | None = None  # Fehlermeldung, falls der erste Versuch ungültig war


class Agent(Protocol):
    """Alles, was eine `handeln`-Methode hat, kann mitspielen."""

    def handeln(self, zug: Zug) -> Aktion: ...
