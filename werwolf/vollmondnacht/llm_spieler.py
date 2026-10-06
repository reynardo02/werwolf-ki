"""LLM-Spieler für Vollmondnacht: eigene Prompts, Rollenhinweise und Tools.

Erbt den Ablauf (LLM fragen, Tool-Call in Aktion übersetzen) vom klassischen
LLMSpieler und tauscht nur aus, was sich zwischen den Spielen unterscheidet.
"""

from pathlib import Path
from typing import Any

from core.tools import ToolSchema
from werwolf.llm_spieler import LLMSpieler, _liste
from werwolf.schnittstelle import ABSTIMMEN, SPRECHEN, Zug
from werwolf.vollmondnacht.engine import (
    MITTE_ANSEHEN,
    NACHAHMEN,
    NICHTS_TUN,
    RAUBEN,
    SPIELER_ANSEHEN,
    VERTAUSCHEN,
)
from werwolf.vollmondnacht.rollen import Partei, Rolle, faehigkeiten_text

# Wer lügen darf, hängt von der Partei ab: Werwölfe und Gerber profitieren vom Lügen,
# das Dorf von Ehrlichkeit – nur so lassen sich die nächtlichen Kartentausche aufklären.
LUEGEN = " Du darfst lügen und jede Rolle behaupten."
EHRLICH = (
    " Das Dorf gewinnt durch Ehrlichkeit: Sag offen, welche Karte du zu Beginn hattest und "
    "was du nachts getan und gesehen hast. Wurde deine Karte vertauscht, weißt du es eventuell nicht."
)
# Experiment 4: Das Dorf erkannte oft den Lügner, stimmte aber gegen ihn, obwohl seine
# Werwolf-Karte nachts schon bei jemand anderem lag. Deshalb ein Hinweis zum Kartenweg.
KARTENWEG = (
    " Verfolge den Weg der Karten: Nachts handelt jeder mit seiner Startkarte, auch wenn sie ihm "
    "vorher geraubt oder vertauscht wurde – nennen zwei Spieler dieselbe Karte, kann das also "
    "ehrlich sein. Gewonnen wird aber mit der Endkarte: Wurde ein Werwolf nachts beraubt oder "
    "vertauscht, liegt seine Werwolf-Karte jetzt beim anderen. Stimme gegen den, der sie jetzt hat."
)

# Kurze Strategie-Hinweise, angelehnt an die Tipps der Anleitung.
ROLLEN_HINWEISE = {
    Rolle.WERWOLF: (
        "Du gehörst zum Werwolfsrudel. Behaupte eine andere Rolle, am besten eine, deren Karte "
        "in der Mitte liegt, und lenke den Verdacht auf andere. Kein Werwolf darf sterben."
    ),
    Rolle.GUENSTLING: (
        "Du gehörst zum Werwolfsrudel, die Werwölfe kennen dich aber nicht. Schütze sie. "
        "Stirbst du statt eines Werwolfs, gewinnt ihr trotzdem – du darfst dich verdächtig machen."
    ),
    Rolle.SEHERIN: "Dein Wissen entlarvt Lügner. Überlege, wann du es teilst.",
    Rolle.RAEUBER: (
        "Hast du nachts eine Karte geraubt, zählt deine neue Karte: Bist du jetzt Werwolf, "
        "spielst du für das Werwolfsrudel und darfst lügen."
    ),
    Rolle.UNRUHESTIFTERIN: (
        "Es kann helfen, offen zu sagen, wessen Karten du vertauscht hast – die beiden "
        "gehören jetzt zur Partei ihrer neuen Karte."
    ),
    Rolle.BETRUNKENER: "Du hast deine Karte mit der Mitte getauscht und weißt nicht, was du jetzt bist.",
    Rolle.SCHLAFLOSE: "Du siehst am Ende der Nacht, welche Karte vor dir liegt.",
    Rolle.FREIMAURER: "Freimaurer können sich gegenseitig ein Alibi geben.",
    Rolle.JAEGER: "Stirbst du, stirbt auch der Spieler, auf den du zeigst – zeige auf einen Werwolf.",
    Rolle.GERBER: (
        "Du bist deine eigene Partei und gewinnst nur, wenn du stirbst. Mach dich verdächtig, "
        "aber nicht zu offensichtlich."
    ),
    Rolle.DORFBEWOHNER: "Die Werwölfe werden behaupten, Dorfbewohner zu sein – pass genau auf.",
    Rolle.DOPPELGAENGERIN: (
        "Nachts übernimmst du die Rolle eines Mitspielers und gehörst dann zu dessen Partei. "
        "Wirst du Werwolf oder Günstling, darfst du lügen, sonst hilft dem Dorf die Wahrheit."
    ),
}

AUFGABEN = {
    NACHAHMEN: "Nacht: Sieh dir die Karte eines Mitspielers an und übernimm seine Rolle. Nutze das Tool nachahmen.",
    SPIELER_ANSEHEN: (
        "Nacht: Als Seherin siehst du dir entweder die Karte eines Mitspielers an (Tool spieler_ansehen) "
        "oder zwei Karten aus der Mitte (Tool mitte_ansehen)."
    ),
    RAUBEN: (
        "Nacht: Als Räuber darfst du deine Karte mit der eines Mitspielers tauschen und dir die neue "
        "ansehen (Tool rauben) – oder nichts tun (Tool nichts_tun)."
    ),
    VERTAUSCHEN: (
        "Nacht: Als Unruhestifterin darfst du die Karten von zwei anderen Spielern vertauschen, "
        "ohne sie anzusehen (Tool vertauschen) – oder nichts tun (Tool nichts_tun)."
    ),
    SPRECHEN: (
        "Diskussion: Du bist dran. Geh auf das Gesagte ein: Behaupte eine Rolle, teile (oder erfinde) "
        "was du nachts gesehen hast, äußere Verdacht oder stell eine Frage. Wiederhole dich nicht. "
        "Nutze das Tool sprechen."
    ),
    ABSTIMMEN: (
        "Abstimmung: Alle zeigen gleichzeitig auf einen Mitspieler. Wer die meisten Stimmen hat, stirbt. "
        "Auf wen zeigst du? Nutze das Tool abstimmen."
    ),
}

# Manche Spieler (vor allem Werwölfe) redeten herum, ohne je eine Karte zu nennen.
# Am Tisch fragt man das als Erstes – daher Pflicht in der ersten Wortmeldung.
ERSTE_REDE = (
    "\n\nDas ist deine erste Wortmeldung: Sag als Erstes, welche Karte du zu Beginn hattest "
    "und was du nachts getan oder gesehen hast."
)

BESCHREIBUNGEN = {
    NACHAHMEN: "Sieh dir die Karte eines Mitspielers an und übernimm seine Rolle und Partei.",
    SPIELER_ANSEHEN: "Sieh dir heimlich die Karte eines Mitspielers an.",
    MITTE_ANSEHEN: "Sieh dir zwei der drei Karten in der Mitte an.",
    RAUBEN: "Tausche deine Karte mit der eines Mitspielers und sieh dir deine neue Karte an.",
    VERTAUSCHEN: "Vertausche die Karten von zwei anderen Spielern, ohne sie anzusehen.",
    NICHTS_TUN: "Verzichte auf deine Nachtaktion.",
    SPRECHEN: "Sag etwas in der Diskussion. Alle hören es.",
    ABSTIMMEN: "Zeige auf den Mitspieler, der sterben soll.",
}

_TEXT = {
    SPRECHEN: {"text": {"type": "string", "description": "Was du sagst, 1–3 Sätze."}},
}
_BEGRUENDUNG = {"type": "string", "description": "Deine ehrliche, private Begründung. Niemand sieht sie."}


def _schon_gesprochen(zug: Zug) -> bool:
    return any(e.art == "rede" and e.daten.get("spieler") == zug.ich for e in zug.ereignisse)


def rollen_im_spiel(zug: Zug) -> set[Rolle]:
    """Welche Rollen diese Partie hat – steht in der öffentlichen Ansage zu Spielbeginn."""
    for e in zug.ereignisse:
        if e.art == "karten":
            return {Rolle(name) for name in e.daten["karten"].split(", ")}
    return set(Rolle)  # ohne Ansage (z. B. in Tests): alle Rollen erklären


def rollen_hinweis(rolle: Rolle) -> str:
    """Strategie-Hinweis plus, je nach Partei der Startkarte, Lügen oder Ehrlichkeit."""
    if rolle is Rolle.DOPPELGAENGERIN:
        return ROLLEN_HINWEISE[rolle]  # Partei steht erst nach dem Nachahmen fest
    return ROLLEN_HINWEISE[rolle] + (EHRLICH + KARTENWEG if rolle.partei is Partei.DORF else LUEGEN)


class VollmondLLMSpieler(LLMSpieler):
    PROMPT_ORDNER = Path(__file__).parent / "prompts"

    def system_prompt(self, zug: Zug) -> str:
        return self._system_vorlage.format(
            name=zug.ich,
            rolle=zug.rolle.value,
            rollen_hinweis=rollen_hinweis(zug.rolle),
            persoenlichkeit=self.persoenlichkeit,
            rollen_im_spiel=faehigkeiten_text(rollen_im_spiel(zug)),
        )

    def zug_prompt(self, zug: Zug) -> str:
        aufgabe = AUFGABEN[zug.erlaubte_tools[0]]
        if zug.erlaubte_tools[0] == SPRECHEN and not _schon_gesprochen(zug):
            aufgabe += ERSTE_REDE
        if zug.hinweis:
            aufgabe += f"\n\nDein letzter Versuch war ungültig: {zug.hinweis} Versuch es noch einmal."
        return self._zug_vorlage.format(
            phase=zug.phase.value,
            spieler=", ".join(self.gemischt([n for n in zug.lebende if n != zug.ich])),
            geheimwissen=_liste(zug.geheimwissen),
            # Nur eine Runde: Der ganze Verlauf passt in den Kontext, kein Kürzen nötig.
            ereignisse=_liste([e.text for e in zug.ereignisse]),
            aufgabe=aufgabe,
        )

    def tools(self, zug: Zug) -> list[ToolSchema]:
        # Eine gemischte Reihenfolge pro Zug, für alle Parameter gleich – so stehen
        # bei der Unruhestifterin ziel1 und ziel2 in derselben Reihenfolge.
        platz = {name: i for i, name in enumerate(self.gemischt(zug.lebende))}
        schemas = []
        for tool in zug.erlaubte_tools:
            parameter: dict[str, dict[str, Any]] = dict(_TEXT.get(tool, {}))
            for name, werte in zug.optionen.get(tool, {}).items():
                parameter[name] = {
                    "type": "string",
                    "enum": sorted(werte, key=lambda n: platz.get(n, 0)),
                    "description": "Name des Spielers",
                }
            if tool == ABSTIMMEN:
                parameter["begruendung"] = _BEGRUENDUNG
            pflicht = tuple(p for p in parameter if p != "begruendung")
            schemas.append(ToolSchema(tool, BESCHREIBUNGEN[tool], parameter, pflicht))
        return schemas
