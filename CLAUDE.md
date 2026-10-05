# Werwolf-KI

LLM-Agenten spielen Werwolf gegeneinander. Einsteigerprojekt, der Agenten-Kern
wird später für eine Agenten-Simulation wiederverwendet.

## Architektur
- core/: Agent, Gedächtnis, LLM-Client, Tool-Schemas. Kennt KEINE Werwolf-Regeln.
- werwolf/: Engine, Rollen, Prompts, MockAgent, LLMSpieler. Kennt KEIN LLM-SDK,
  nur die Schnittstelle `core.llm_client.LLMClient`.
- werwolf/vollmondnacht/: zweite Spielvariante „Werwölfe Vollmondnacht“ (Ravensburger):
  eine Nacht, ein Tag, eine gleichzeitige Abstimmung, 12 Rollen, Szenarien aus der Anleitung.
  Nutzt Schnittstelle, MockAgent, Protokoll und Log von werwolf/ mit.
- Nur core/llm_client.py importiert das openai-SDK (OpenAI-kompatibles Format).
- main.py startet eine Partie. logs/ für JSONL und Spielprotokolle.
- web/: Web-Oberfläche ohne Framework (http.server + eine HTML-Seite). Die Partie läuft in einem
  Thread, der Browser fragt den Stand per Polling ab. Er bekommt nur Öffentliches und dein Geheimwissen.

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
  (`--llm alle` für eine reine LLM-Partie). Protokoll und Log landen in `logs/partie_*.txt/.jsonl`.
- Viele Partien: `.venv/bin/python main.py --partien 20` (mit `--llm …` kombinierbar)
- Vollmondnacht: `.venv/bin/python main.py --regeln vollmondnacht --spieler 7 [--szenario Payback]`
- Selbst mitspielen: `.venv/bin/python main.py --regeln vollmondnacht --mensch [NAME] --llm alle`
  (Konsole zeigt nur Öffentliches, Geheimnisse danach im Protokoll)
- Eigene Bilanz: `.venv/bin/python auswerten.py --mensch` (nur Vollmondnacht-Partien mit Mensch)
- Im Browser spielen: `.venv/bin/python -m web` (öffnet http://127.0.0.1:8000/, `--port`, `--kein-browser`)
- Auswertung: `.venv/bin/python auswerten.py` (alle Logs) oder mit Muster, z. B. `"logs/partie_2026*.jsonl"`

## Aktueller Stand
Meilenstein 1: Engine ohne KI – umgesetzt (Engine, Rollen, MockAgent, Tests).
Meilenstein 2: Erster LLM-Agent – umgesetzt (LLM-Client, Tool-Schemas, LLMSpieler,
Konfiguration über .env, Budget-Limit, Tests mit Fake-Client).
Meilenstein 3: Alle Agenten als LLM – umgesetzt (Persönlichkeiten in
werwolf/prompts/persoenlichkeiten.txt, gekürztes Gedächtnis über core/gedaechtnis.py,
lesbares Protokoll über werwolf/protokoll.py, Tempolimit LLM_MAX_PRO_MINUTE).
Mit `--llm alle` und gemini-3.5-flash-lite geprüft: Partie ohne API-Fehler, Werwölfe
lügen öffentlich und planen in ihren Notizen, Dorfbewohner verdächtigen sich gegenseitig.
Meilenstein 4: Auswertung – umgesetzt (Ereignisse mit `art`/`daten`, JSONL-Log über
werwolf/jsonl_log.py, Statistik über werwolf/auswertung.py, Skript auswerten.py).
Mit 12 LLM-Partien geprüft: Werwölfe gewinnen alle, das Dorf stimmt bei der öffentlichen
Reihum-Abstimmung schlechter als Zufall (Herdenverhalten).
Zusatz: Spielvariante Vollmondnacht – umgesetzt (alle 12 Rollen inkl. Doppelgängerin,
alle Szenarien, VollmondLLMSpieler, eigene Auswertung).
Meilenstein 5, Teil 1: Selbst mitspielen – umgesetzt (werwolf/mensch_spieler.py, `--mensch`,
beide Varianten; Partien mit Mensch bilden in der Auswertung eine eigene Gruppe).
Meilenstein 5, Teil 2: Web-Oberfläche – umgesetzt (web/sitzung.py, web/server.py, web/static/index.html;
getestet mit Sitzungs- und HTTP-Tests sowie per Playwright im Browser).

## Experimente (Vollmondnacht, Konfusion, 7 Spieler, gemini-3.5-flash-lite, Seeds 443803–443812)
Immer nur eine Änderung gegenüber Serie 1, Kennzahl: Dorf-Stimmen gegen Werwölfe (Zufall 24,2 %).
- Serie 1, Ausgangspunkt: 27,3 %, Dorf gewinnt 2/10.
- Serie 2, Logik-Hinweis „doppelte Rollenbehauptung = Lüge“: 12,7 %, 0/10. Verworfen:
  Das Dorf hielt ehrliche Kartentauscher für Lügner, Werwölfe nutzten den Hinweis aus.
- Serie 3, Lügen nur für Werwolf/Günstling/Gerber, Ehrlichkeit fürs Dorf: 47,3 %, 4/10. Übernommen.
  Hauptfehler danach: Das Dorf verfolgt nicht, wohin eine Werwolf-Karte getauscht wurde.
- Positions-Verzerrung behoben (LLMs wählten meist den ersten Namen). Kontrollserie damit:
  16,4 %, 1/10 – neue Basis. Serie 3 war durch die Verzerrung geschönt bzw. 10 Partien streuen stark.
  Das Dorf stimmt in der Kontrollserie zu 50 % gegen die Start-Werwölfe, aber nur zu 14 % gegen
  die End-Werwölfe: In 4 Partien starb der ursprüngliche Werwolf, dessen Karte aber getauscht war.
- Serie 4, Hinweis zum Kartenweg fürs Dorf (KARTENWEG in vollmondnacht/llm_spieler.py),
  20 Partien ab Seed 443803: 43,5 % (Zufall 25,9 %), Dorf gewinnt 8/20. Übernommen.
  Stimmen gegen Start-Werwölfe 44,4 % – die Lücke zur Endkarte ist geschlossen.
  Siege 1/10 → 8/20 ist allein noch nicht sicher (Fisher-Test p ≈ 0,1), die Stimmen sind deutlicher.
  Restfehler (Logs 6–20): Kartenweg nur noch 1× übersehen. Häufigster Fehler jetzt: Das Dorf kennt
  die Nachtreihenfolge nicht und hält ehrliche Tauscher für Lügner (5×, z. B. Räuber raubt
  Unruhestifterin, die danach noch tauscht). Dazu falsche Behauptungen von Rollen aus der Mitte (4×).
- Serie 5, Spielleiter sagt allen die Nachtreihenfolge an (karten-Ereignis in vollmondnacht/engine.py):
  37,4 % (Zufall 26,8 %), Dorf gewinnt 6/20 – kein messbarer Effekt, Unterschied zu Serie 4 im
  Rauschen. Bleibt drin, weil es der echten Regel entspricht (der Spielleiter ruft laut auf).
  Logs 1–20: Die Reihenfolge wird nur 2× erwähnt, das Modell nutzt die Ansage kaum. Kartenweg wirkt
  (3 Siege gegen getauschte Werwölfe). 14 Niederlagen: 9× stirbt ein ehrlicher Spieler mit Info
  (Tauscher, Seherin, Schlaflose), 3× Kartenweg übersehen, 2× einfacher Dorfbewohner.
  Prompt-Hinweise stoßen bei gemini-3.5-flash-lite an Grenzen.
- Idee: Persönlichkeit „lenkt gern vom Thema ab“ schadet.
Als Nächstes: offen – z. B. stärkeres Modell vergleichen oder Agenten-Kern für die Simulation herauslösen.
