# Werwolf-KI

LLM-Agenten spielen Werwolf gegeneinander. Einsteigerprojekt, der Agenten-Kern
wird später für eine Agenten-Simulation wiederverwendet.

## Architektur
- core/: Agent, Gedächtnis, LLM-Client, Tool-Schemas. Kennt KEINE Werwolf-Regeln.
- werwolf/: Engine, Rollen, Prompts, MockAgent. Kennt KEIN LLM-SDK.
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

## Aktueller Stand
Meilenstein 1: Engine ohne KI – umgesetzt (Engine, Rollen, MockAgent, Tests).
Als Nächstes: Meilenstein 2, erster LLM-Agent über `werwolf/schnittstelle.py`.