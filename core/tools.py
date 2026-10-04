"""Tool-Schemas und Tool-Calls – unabhängig von Spiel und LLM-Anbieter."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSchema:
    """Beschreibt ein Tool, das ein LLM aufrufen darf.

    `parameter` ist ein JSON-Schema für die Eigenschaften (properties),
    `pflicht` die Namen der Pflichtparameter.
    """

    name: str
    beschreibung: str
    parameter: dict[str, dict[str, Any]] = field(default_factory=dict)
    pflicht: tuple[str, ...] = ()

    def als_openai(self) -> dict[str, Any]:
        """Wandelt das Schema in das OpenAI-kompatible Format um."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.beschreibung,
                "parameters": {
                    "type": "object",
                    "properties": self.parameter,
                    "required": list(self.pflicht),
                },
            },
        }


@dataclass(frozen=True)
class ToolCall:
    """Ein Tool-Aufruf, den das LLM zurückgegeben hat."""

    name: str
    argumente: dict[str, Any]
