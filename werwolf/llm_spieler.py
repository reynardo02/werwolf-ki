"""Ein Spieler, der seine Züge von einem LLM entscheiden lässt.

Er übersetzt in beide Richtungen:
  Zug (Engine)  ->  Prompt + Tool-Schemas (LLM)
  Tool-Call     ->  Aktion (Engine)
Den eigentlichen LLM-Aufruf erledigt ein `LLMClient` aus core/ – deshalb kennt
dieses Modul kein SDK und lässt sich mit einem Fake-Client testen.
"""

from pathlib import Path

from core.llm_client import LLMClient, LLMFehler
from werwolf.roles import Rolle, Team
from werwolf.schnittstelle import (
    ABSTIMMEN,
    NOTIZ_SCHREIBEN,
    OPFER_WAEHLEN,
    PRUEFEN,
    SPRECHEN,
    Aktion,
    Zug,
)
from werwolf.werkzeuge import tool_schemas

PROMPTS = Path(__file__).parent / "prompts"

ROLLEN_HINWEISE = {
    Rolle.WERWOLF: (
        "Du darfst lügen und bluffen. Verrate niemals, dass du ein Werwolf bist, "
        "und lenke den Verdacht auf andere."
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
    SPRECHEN: "Diskussion: Du bist dran. Nutze das Tool sprechen.",
    ABSTIMMEN: "Abstimmung: Wen soll das Dorf hinrichten? Nutze das Tool abstimmen.",
    OPFER_WAEHLEN: "Nacht: Wählt euer Opfer. Nutze das Tool opfer_waehlen.",
    PRUEFEN: "Nacht: Wen willst du prüfen? Nutze das Tool pruefen.",
    NOTIZ_SCHREIBEN: "Die Runde ist vorbei. Halte deine Einschätzung fest. Nutze das Tool notiz_schreiben.",
}


def _liste(eintraege: list[str], leer: str = "(nichts)") -> str:
    return "\n".join(f"- {e}" for e in eintraege) if eintraege else leer


class LLMSpieler:
    def __init__(self, client: LLMClient, persoenlichkeit: str = "ruhig und aufmerksam") -> None:
        self.client = client
        self.persoenlichkeit = persoenlichkeit
        self._system_vorlage = (PROMPTS / "system.txt").read_text(encoding="utf-8")
        self._zug_vorlage = (PROMPTS / "zug.txt").read_text(encoding="utf-8")

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
            lebende=", ".join(zug.lebende),
            geheimwissen=_liste(zug.geheimwissen),
            notizen=_liste(zug.notizen),
            ereignisse=_liste([f"[Runde {e.runde}] {e.text}" for e in zug.ereignisse]),
            aufgabe=aufgabe,
        )

    def handeln(self, zug: Zug) -> Aktion:
        # Die Engine nennt die gültigen Ziele (z. B. ohne Mitwerwolf).
        ziele = zug.ziele or [name for name in zug.lebende if name != zug.ich]
        try:
            antwort = self.client.anfragen(
                self.system_prompt(zug),
                self.zug_prompt(zug),
                tool_schemas(zug.erlaubte_tools, ziele),
            )
        except LLMFehler:
            # Eine leere Aktion ist ungültig: Die Engine gibt einen zweiten
            # Versuch und wählt danach zufällig. Das Spiel läuft also weiter.
            return Aktion("")

        if antwort.tool_call is None:
            return Aktion("")
        # Alle Parameter als Text, so wie die Engine sie erwartet.
        parameter = {k: str(v) for k, v in antwort.tool_call.argumente.items()}
        return Aktion(antwort.tool_call.name, parameter)
