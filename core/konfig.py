"""Liest die LLM-Einstellungen aus der .env-Datei bzw. aus Umgebungsvariablen."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.llm_client import OpenAIKompatiblerClient
from core.schnittstellen import CHAT, SCHNITTSTELLEN


@dataclass(frozen=True)
class LLMKonfig:
    base_url: str
    modell: str
    api_key: str
    temperatur: float = 0.9
    max_aufrufe: int = 400
    tool_choice: str = "required"
    max_pro_minute: int = 0
    schnittstelle: str = CHAT

    def client(self) -> OpenAIKompatiblerClient:
        return OpenAIKompatiblerClient(
            base_url=self.base_url,
            modell=self.modell,
            api_key=self.api_key,
            temperatur=self.temperatur,
            max_aufrufe=self.max_aufrufe,
            tool_choice=self.tool_choice,
            max_pro_minute=self.max_pro_minute,
            schnittstelle=self.schnittstelle,
        )


def konfig_laden(env_datei: str | None = ".env") -> LLMKonfig:
    """Lädt LLM_BASE_URL, LLM_MODEL, LLM_API_KEY und optionale Einstellungen.

    Absichtlich NICHT ANTHROPIC_API_KEY: Diese Variable würde Claude Code dazu
    bringen, über API-Guthaben statt über dein Abo abzurechnen.
    """
    if env_datei:
        load_dotenv(env_datei)

    base_url = os.getenv("LLM_BASE_URL", "").strip()
    modell = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()

    fehlend = [n for n, w in [("LLM_BASE_URL", base_url), ("LLM_MODEL", modell)] if not w]
    # Lokale Server wie Ollama brauchen keinen echten Key, das SDK aber irgendeinen.
    lokal = "localhost" in base_url or "127.0.0.1" in base_url
    if not api_key:
        if lokal:
            api_key = "lokal"
        else:
            fehlend.append("LLM_API_KEY")
    if fehlend:
        raise ValueError(f"Fehlende Einstellungen in der .env: {', '.join(fehlend)}")
    # "responses" für OpenAIs GPT-6-Modelle (Tools beim Nachdenken nur dort), sonst "chat".
    schnittstelle = os.getenv("LLM_SCHNITTSTELLE", CHAT).strip().lower()
    if schnittstelle not in SCHNITTSTELLEN:
        raise ValueError(f"LLM_SCHNITTSTELLE muss {' oder '.join(SCHNITTSTELLEN)} sein, nicht '{schnittstelle}'")

    return LLMKonfig(
        base_url=base_url,
        modell=modell,
        api_key=api_key,
        temperatur=float(os.getenv("LLM_TEMPERATUR", "0.9")),
        max_aufrufe=int(os.getenv("LLM_MAX_AUFRUFE", "400")),
        tool_choice=os.getenv("LLM_TOOL_CHOICE", "required"),
        max_pro_minute=int(os.getenv("LLM_MAX_PRO_MINUTE", "0")),
        schnittstelle=schnittstelle,
    )
