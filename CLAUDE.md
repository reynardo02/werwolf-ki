# Werwolf-KI

LLM-Agenten spielen Werwolf gegeneinander. Einsteigerprojekt, der Agenten-Kern
wird später für eine Agenten-Simulation wiederverwendet.

## Architektur
- core/: Agent, Gedächtnis, LLM-Client, Tool-Schemas. Kennt KEINE Werwolf-Regeln.
- werwolf/: Engine, Rollen, Prompts, MockAgent, LLMSpieler. Kennt KEIN LLM-SDK,
  nur die Schnittstelle `core.llm_client.LLMClient`.
- Nur core/llm_client.py importiert das openai-SDK (OpenAI-kompatibles Format).
- main.py startet eine Partie. logs/ für JSONL und Spielprotokolle.

## Konventionen
- Python 3.12, Typ-Hints, dataclasses
- Tests mit pytest in tests/, Engine immer mit MockAgent testbar
- Deutsche Kommentare und Bezeichner
- API-Keys nur über .env, nie im Code

## Arbeitsweise
- Ich lerne mit diesem Projekt: erkläre Entscheidungen kurz.
- Kleine Schritte, nach jedem Schritt Tests ausführen.

## Befehle
- Einrichten: `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- Tests: `.venv/bin/pytest`
- Partie: `.venv/bin/python main.py --seed 1 --spieler 7`
- Partie mit LLM: `.env` aus `.env.example` anlegen, dann `.venv/bin/python main.py --llm 1`
  (`--llm alle` für eine reine LLM-Partie). Das Protokoll landet in `logs/partie_*.txt`.

## Aktueller Stand
Meilenstein 1: Engine ohne KI – umgesetzt (Engine, Rollen, MockAgent, Tests).
Meilenstein 2: Erster LLM-Agent – umgesetzt (LLM-Client, Tool-Schemas, LLMSpieler,
Konfiguration über .env, Budget-Limit, Tests mit Fake-Client).
Meilenstein 3: Alle Agenten als LLM – umgesetzt (Persönlichkeiten in
werwolf/prompts/persoenlichkeiten.txt, gekürztes Gedächtnis über core/gedaechtnis.py,
lesbares Protokoll über werwolf/protokoll.py). Offen: echte Partie mit `--llm alle` prüfen.
Als Nächstes: Meilenstein 4, JSON-Logs und Auswertung über viele Partien.
