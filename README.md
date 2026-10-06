# Werwolf-KI

KI-Agenten (LLMs) spielen Werwolf gegeneinander – und du kannst mitspielen.

**▶ Jetzt im Browser spielen: https://reynardo02.github.io/werwolf-ki/**

Kein Download und keine Anmeldung nötig. Beim ersten Aufruf lädt die Seite Python in
den Browser (ca. 13 MB), danach geht es sofort los.

## Spielvarianten

- **Werwölfe Vollmondnacht** (nach dem Spiel von Ravensburger): eine Nacht, ein Tag, eine
  gleichzeitige Abstimmung. Nachts werden Karten angesehen, geraubt und vertauscht. Am Ende
  zählt die Karte, die vor dir liegt, auch wenn sie ohne dein Wissen getauscht wurde.
  12 Rollen und die Szenarien aus der Anleitung.
- **Klassisch:** mehrere Runden aus Nacht und Tag, mit Werwölfen, Seherin und Dorfbewohnern.

## Mit KI-Mitspielern spielen

Für LLM-Mitspieler brauchst du einen eigenen API-Key eines OpenAI-kompatiblen Anbieters,
zum Beispiel kostenlos bei [Google AI Studio](https://aistudio.google.com) („Get API key“)
oder bei [OpenAI](https://platform.openai.com/api-keys). Trag ihn auf der Seite unten bei
**„LLM-Zugang“** ein und wähle den Anbieter – Adresse und Modell werden dann eingetragen.

- **Google Gemini** (`gemini-3.5-flash-lite`): günstig, im kostenlosen Tarif nutzbar.
- **OpenAI** (`gpt-5.4-mini`): spielt in unseren Tests deutlich logischer, kostet aber ein paar Cent pro Partie.

- Der Key bleibt in deinem Browser und wird nur an den LLM-Anbieter geschickt.
- Ohne Key wählst du bei „LLM-Mitspieler“ **„keine“** und spielst gegen einfache Zufallsspieler.
- Am Ende kannst du das komplette Protokoll mit allen Geheimnissen herunterladen.

## Lokal ausführen

Voraussetzung: Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # API-Key eintragen
```

| Was | Befehl |
|---|---|
| Im Browser spielen (lokaler Server) | `.venv/bin/python -m web` |
| In der Konsole mitspielen | `.venv/bin/python main.py --regeln vollmondnacht --mensch --llm alle` |
| KI gegen KI | `.venv/bin/python main.py --regeln vollmondnacht --llm alle` |
| Viele Partien für Statistiken | `.venv/bin/python main.py --regeln vollmondnacht --llm alle --partien 20` |
| Auswerten | `.venv/bin/python auswerten.py` (eigene Partien: `--mensch`) |
| Tests | `.venv/bin/pytest` |

Unter Windows heißt der Pfad `.venv\Scripts\python` statt `.venv/bin/python`.

## Aufbau

- `core/` – Agenten-Kern: LLM-Client, Tool-Schemas, Gedächtnis. Kennt keine Spielregeln.
- `werwolf/` – Engine, Rollen, Prompts und Spieler (LLM, Zufall, Mensch); `werwolf/vollmondnacht/`
  für die zweite Variante.
- `web/` – Web-Oberfläche: lokaler Server oder, auf GitHub Pages, Python im Browser (Pyodide).
- `main.py`, `auswerten.py` – Partien starten und auswerten.

Details, Experimente und Ergebnisse stehen in [CLAUDE.md](CLAUDE.md).
