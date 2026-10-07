"""Ein Spieler, der seine Züge von einem LLM entscheiden lässt.

Er übersetzt in beide Richtungen:
  Zug (Engine)  ->  Prompt + Tool-Schemas (LLM)
  Tool-Call     ->  Aktion (Engine)
Den eigentlichen LLM-Aufruf erledigt ein `LLMClient` aus core/ – deshalb kennt
dieses Modul kein SDK und lässt sich mit einem Fake-Client testen.
"""

import random
from pathlib import Path

from core.gedaechtnis import Erinnerung, kontext_auswaehlen
from core.llm_client import LLMClient, LLMFehler
from core.tools import ToolSchema
from werwolf.roles import Rolle, Team
from werwolf.schnittstelle import (
    ABSTIMMEN,
    NOTIZ_SCHREIBEN,
    OPFER_WAEHLEN,
    PRUEFEN,
    SPRECHEN,
    Aktion,
    Phase,
    Zug,
)
from werwolf.werkzeuge import tool_schemas

PROMPTS = Path(__file__).parent / "prompts"

ROLLEN_HINWEISE = {
    Rolle.WERWOLF: (
        "Du darfst lügen und bluffen, auch eine falsche Rolle behaupten. Verrate niemals, "
        "dass du ein Werwolf bist, lenke den Verdacht auf andere und schütze deinen "
        "Mitwolf, ohne dass es auffällt."
    ),
    Rolle.SEHERIN: (
        "Dein Wissen ist wertvoll, aber wenn du dich zu früh zu erkennen gibst, "
        "fressen dich die Werwölfe. Überlege, wann du es teilst."
    ),
    Rolle.DORFBEWOHNER: "Du hast keine Sonderfähigkeit. Beobachte genau, wer sich verdächtig verhält.",
}

ZIELE = {
    Team.DORF: "Finde und eliminiere alle Werwölfe.",
    Team.WERWOELFE: "Überlebe und eliminiere die Dorfbewohner, bis ihr Werwölfe in der Mehrheit seid.",
}

AUFGABEN = {
    SPRECHEN: (
        "Diskussion: Du bist dran. Geh auf das Gesagte ein: Äußere einen konkreten Verdacht, "
        "verteidige dich oder stell jemandem eine Frage. Wiederhole dich nicht. "
        "Nutze das Tool sprechen."
    ),
    ABSTIMMEN: "Abstimmung: Wen soll das Dorf hinrichten? Nutze das Tool abstimmen.",
    OPFER_WAEHLEN: "Nacht: Wählt euer Opfer. Nutze das Tool opfer_waehlen.",
    PRUEFEN: "Nacht: Wen willst du prüfen? Nutze das Tool pruefen.",
    NOTIZ_SCHREIBEN: (
        "Die Runde ist vorbei. Die Diskussion dieser Runde siehst du später nicht mehr, "
        "nur diese Notiz. Halte fest, wem du traust, wen du verdächtigst und warum. "
        "Nutze das Tool notiz_schreiben."
    ),
}


def persoenlichkeiten_laden() -> list[str]:
    """Liest die Persönlichkeiten aus der Vorlage, eine pro Zeile."""
    zeilen = (PROMPTS / "persoenlichkeiten.txt").read_text(encoding="utf-8").splitlines()
    return [z.strip() for z in zeilen if z.strip() and not z.startswith("#")]


def _liste(eintraege: list[str], leer: str = "(nichts)") -> str:
    return "\n".join(f"- {e}" for e in eintraege) if eintraege else leer


class LLMSpieler:
    # Unterklassen (z. B. für Vollmondnacht) bringen eigene Vorlagen mit.
    PROMPT_ORDNER = PROMPTS

    def __init__(
        self,
        client: LLMClient,
        persoenlichkeit: str = "ruhig und aufmerksam",
        volle_runden: int = 1,
        rng: random.Random | None = None,
    ) -> None:
        self.client = client
        self.persoenlichkeit = persoenlichkeit
        # Zum Mischen von Namenslisten (siehe gemischt). Eigener Generator, damit
        # die Partie selbst bei gleichem Seed gleich verteilt wird.
        self.rng = rng or random.Random()
        self._platz: dict[str, float] = {}  # Name -> fester Zufallswert fürs Mischen
        # Wie viele Runden das LLM komplett sieht. Ältere Diskussionen kennt es
        # nur noch aus seinen eigenen Notizen.
        self.volle_runden = volle_runden
        self._system_vorlage = (self.PROMPT_ORDNER / "system.txt").read_text(encoding="utf-8")
        self._zug_vorlage = (self.PROMPT_ORDNER / "zug.txt").read_text(encoding="utf-8")

    def system_prompt(self, zug: Zug) -> str:
        return self._system_vorlage.format(
            name=zug.ich,
            rolle=zug.rolle.value,
            rollen_hinweis=ROLLEN_HINWEISE[zug.rolle],
            ziel=ZIELE[zug.rolle.team],
            persoenlichkeit=self.persoenlichkeit,
        )

    def zug_prompt(self, zug: Zug) -> str:
        aufgabe = "\n".join(AUFGABEN[t] for t in zug.erlaubte_tools)
        if zug.hinweis:
            aufgabe += f"\n\nDein letzter Versuch war ungültig: {zug.hinweis} Versuch es noch einmal."
        return self._zug_vorlage.format(
            runde=zug.runde,
            phase=zug.phase.value,
            lebende=", ".join(self.gemischt(zug.lebende)),
            geheimwissen=_liste(zug.geheimwissen),
            notizen=_liste(zug.notizen),
            ereignisse=_liste([f"[Runde {e.runde}] {e.text}" for e in self.verlauf(zug)]),
            aufgabe=aufgabe,
        )

    def verlauf(self, zug: Zug) -> list[Erinnerung]:
        """Gekürzter Spielverlauf: Alte Diskussionsbeiträge fallen weg,
        Tode, aufgedeckte Rollen und Abstimmungen bleiben."""
        erinnerungen = [
            Erinnerung(e.runde, e.text, wichtig=e.phase is not Phase.DISKUSSION)
            for e in zug.ereignisse
        ]
        return kontext_auswaehlen(erinnerungen, zug.runde, self.volle_runden)

    def tools(self, zug: Zug) -> list[ToolSchema]:
        # Die Engine nennt die gültigen Ziele (z. B. ohne Mitwerwolf).
        ziele = zug.ziele or [name for name in zug.lebende if name != zug.ich]
        return tool_schemas(zug.erlaubte_tools, self.gemischt(ziele))

    def gemischt(self, namen: list[str]) -> list[str]:
        """Namen in zufälliger, aber für diesen Spieler fester Reihenfolge.

        Kleine Modelle wählen auffällig oft die erste Option einer Liste
        (Positions-Verzerrung). Gemischt hat kein Spieler einen Platzvorteil.
        Jeder Spieler würfelt die Reihenfolge nur einmal: So bleibt der Anfang
        seiner Anfragen von Zug zu Zug gleich, und der Anbieter kann ihn cachen
        (Prompt Caching, billiger). Neu gemischt bei jedem Aufruf ginge das nicht.
        """
        for name in namen:
            if name not in self._platz:
                self._platz[name] = self.rng.random()
        return sorted(namen, key=self._platz.__getitem__)

    def handeln(self, zug: Zug) -> Aktion:
        try:
            antwort = self.client.anfragen(self.system_prompt(zug), self.zug_prompt(zug), self.tools(zug))
        except LLMFehler:
            # Eine leere Aktion ist ungültig: Die Engine gibt einen zweiten
            # Versuch und wählt danach zufällig. Das Spiel läuft also weiter.
            return Aktion("")

        if antwort.tool_call is None:
            return Aktion("")
        # Alle Parameter als Text, so wie die Engine sie erwartet.
        parameter = {k: str(v) for k, v in antwort.tool_call.argumente.items()}
        return Aktion(antwort.tool_call.name, parameter)
