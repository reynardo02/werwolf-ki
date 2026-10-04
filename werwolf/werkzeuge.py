"""Die Werwolf-Aktionen als Tool-Schemas, wie das LLM sie sieht."""

from typing import Any

from core.tools import ToolSchema
from werwolf.schnittstelle import ABSTIMMEN, NOTIZ_SCHREIBEN, OPFER_WAEHLEN, PRUEFEN, SPRECHEN


def _ziel(beschreibung: str, ziele: list[str]) -> dict[str, Any]:
    # Die erlaubten Namen als enum helfen dem Modell. Die Engine prüft trotzdem.
    return {"type": "string", "description": beschreibung, "enum": ziele}


_BEGRUENDUNG = {
    "type": "string",
    "description": "Deine ehrliche, private Begründung. Niemand im Spiel sieht sie.",
}


def tool_schemas(tool_namen: list[str], ziele: list[str]) -> list[ToolSchema]:
    """Baut die Schemas für die gerade erlaubten Tools."""
    alle = {
        SPRECHEN: ToolSchema(
            SPRECHEN,
            "Sag etwas in der Diskussion. Alle lebenden Spieler hören es.",
            {"text": {"type": "string", "description": "Was du sagst, 1–3 Sätze."}},
            ("text",),
        ),
        ABSTIMMEN: ToolSchema(
            ABSTIMMEN,
            "Stimme öffentlich dafür, dass ein Spieler ausscheidet.",
            {"ziel": _ziel("Name des Spielers", ziele), "begruendung": _BEGRUENDUNG},
            ("ziel",),
        ),
        OPFER_WAEHLEN: ToolSchema(
            OPFER_WAEHLEN,
            "Nur Werwölfe: Schlage das Opfer dieser Nacht vor.",
            {"ziel": _ziel("Name des Opfers (kein Werwolf)", ziele), "begruendung": _BEGRUENDUNG},
            ("ziel",),
        ),
        PRUEFEN: ToolSchema(
            PRUEFEN,
            "Nur Seherin: Erfahre heimlich die Rolle eines Spielers.",
            {"ziel": _ziel("Name des Spielers", ziele)},
            ("ziel",),
        ),
        NOTIZ_SCHREIBEN: ToolSchema(
            NOTIZ_SCHREIBEN,
            "Schreib eine private Notiz für dich: wem du traust, wen du verdächtigst und warum.",
            {"text": {"type": "string", "description": "Deine Notiz, höchstens 3 Sätze."}},
            ("text",),
        ),
    }
    return [alle[name] for name in tool_namen]
