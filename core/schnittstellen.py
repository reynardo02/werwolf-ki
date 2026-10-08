"""Die zwei Formate der OpenAI-API: Chat Completions (alt) und Responses (neu).

Viele Anbieter (Gemini, DeepSeek, Ollama, …) sprechen nur das alte Chat-Format. OpenAIs
neue Modelle (GPT-6) können Tools und Nachdenken („Reasoning“) aber nur zusammen über die
Responses-Schnittstelle: Bei /chat/completions lehnen sie Tools ab, solange sie nachdenken.

Hier wird nur übersetzt, ohne SDK – so nutzen es der Python-Client und die Browser-Fassung
(Pyodide) gleich. Antworten erkennen ihr Format selbst; gespeicherte Partien mit alten
Chat-Antworten lassen sich also weiter wiederholen.
"""

import json
from dataclasses import dataclass
from typing import Any

from core.tools import ToolCall, ToolSchema

CHAT = "chat"
RESPONSES = "responses"
SCHNITTSTELLEN = (CHAT, RESPONSES)


@dataclass
class Nutzung:
    input_tokens: int = 0
    output_tokens: int = 0
    gecachte_tokens: int = 0


def anfrage_bauen(
    schnittstelle: str, system: str, nachricht: str, tools: list[ToolSchema],
    tool_choice: str = "required", temperatur: float | None = None,
) -> dict[str, Any]:
    """Der Körper einer Anfrage (ohne Modell) im gewünschten Format."""
    if schnittstelle == RESPONSES:
        return {
            "instructions": system,
            "input": [{"role": "user", "content": nachricht}],
            # strict=False: Sonst verlangt die API, dass jeder Parameter Pflicht ist –
            # die Begründung beim Abstimmen ist aber freiwillig.
            "tools": [{"type": "function", **t.als_openai()["function"], "strict": False} for t in tools],
            "tool_choice": tool_choice,
            # Nachdenkende Modelle nehmen keine Temperatur an; nichts speichern bei OpenAI.
            "store": False,
        }
    anfrage: dict[str, Any] = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": nachricht}],
        "tools": [t.als_openai() for t in tools],
        "tool_choice": tool_choice,
    }
    if temperatur is not None:
        anfrage["temperature"] = temperatur
    return anfrage


def _tool_call(name: Any, argumente: Any) -> ToolCall | None:
    """Kaputtes JSON oder kein Objekt zählt als „kein Tool-Call“."""
    try:
        werte = json.loads(argumente or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return ToolCall(str(name), werte) if isinstance(werte, dict) else None


def antwort_lesen(daten: Any) -> tuple[ToolCall | None, str, Nutzung]:
    """Liest eine Antwort in einem der beiden Formate: (Tool-Call oder None, Freitext, Tokens)."""
    if not isinstance(daten, dict):
        return None, "", Nutzung()
    nutzung = daten.get("usage") or {}
    if "output" in daten:  # Responses
        details = nutzung.get("input_tokens_details") or {}
        zahlen = Nutzung(nutzung.get("input_tokens") or 0, nutzung.get("output_tokens") or 0,
                         details.get("cached_tokens") or 0)
        tool_call, text = None, ""
        for teil in daten.get("output") or []:
            if not isinstance(teil, dict):
                continue
            if teil.get("type") == "function_call" and tool_call is None:
                tool_call = _tool_call(teil.get("name"), teil.get("arguments"))
            elif teil.get("type") == "message":
                text += "".join(s.get("text") or "" for s in teil.get("content") or [] if isinstance(s, dict))
        return tool_call, text, zahlen
    # Chat Completions
    details = nutzung.get("prompt_tokens_details") or {}
    zahlen = Nutzung(nutzung.get("prompt_tokens") or 0, nutzung.get("completion_tokens") or 0,
                     details.get("cached_tokens") or 0)
    try:
        nachricht = daten["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None, "", zahlen
    text = nachricht.get("content") or ""
    tool_calls = nachricht.get("tool_calls") or []
    if not tool_calls:
        return None, text, zahlen
    funktion = tool_calls[0].get("function") or {}
    return _tool_call(funktion.get("name"), funktion.get("arguments")), text, zahlen
