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
- GitHub Pages: dieselbe Seite, aber Python läuft per Pyodide im Browser (web/browser.py,
  web/static/pyodide-backend.js). Prinzip „Wiederholen statt Warten“: die Partie wird mit allen
  bisherigen Antworten von vorn gespielt, bis eine fehlt (dein Zug oder ein LLM-Aufruf per fetch
  mit dem Key des Spielers). Gemeinsamer Aufbau in werwolf/aufbau.py und web/einstellungen.py.

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
- GitHub Pages: baut .github/workflows/pages.yml bei jedem Push auf main. Lokal bauen:
  `npm pack pyodide@314.0.7 && tar xzf pyodide-314.0.7.tgz && .venv/bin/python -m web.seite_bauen _site --pyodide package`
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
Zusatz: Online spielbar über GitHub Pages (Pyodide, eigener API-Key im Browser, Partie überlebt Neuladen).

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
- Regel-Fix nach eigenen Partien: Die LLMs kannten nur ihre eigene Rolle. Werwölfe behaupteten
  z. B. „Seherin, eine Mittelkarte angesehen“ (unmöglich: Seherin sieht 1 Spielerkarte oder
  2 Mittelkarten), und das Dorf merkte es nicht. Jetzt stehen die Fähigkeiten aller Rollen der
  Partie im Systemprompt (FAEHIGKEITEN in vollmondnacht/rollen.py). Wirkung noch nicht gemessen.
- Fix: Manche Spieler nannten nie ihre Startkarte. Jetzt verlangt die erste Wortmeldung
  Startkarte und Nachtaktion (ERSTE_REDE in vollmondnacht/llm_spieler.py). Wirkung noch nicht gemessen.
  Konkret mit Namen und Karten: Werwölfe behaupteten „Seherin, zwei Mittelkarten“, ohne sie zu
  nennen. Auch LUEGEN verlangt jetzt passende Einzelheiten zur behaupteten Rolle.
- Fix: Eine Schlaflose, die morgens eine Werwolf-Karte sah, sagte das offen – sie bekam weiter den
  Ehrlichkeits-Hinweis ihrer Startkarte. Jetzt kennt der Zug die zuletzt gesehene eigene Karte
  (`Zug.bekannte_karte`, Räuber/Schlaflose), und der Hinweis richtet sich nach deren Partei (NEUE_PARTEI).
- Persönlichkeit „lenkt gern vom Thema ab“ ersetzt durch „teilt ausführlich die eigenen Gedanken“: In eigenen
  Partien redete sie 3× über Wetter und Kaffee statt über die Partie. Gleiche Anzahl Persönlichkeiten,
  also bleibt die Verteilung bei gleichem Seed gleich.
- Tauscher sprechen die Folge aus (TAUSCH_FOLGE in vollmondnacht/llm_spieler.py): Unruhestifterin und
  Räuber sagen in der ersten Rede, wer jetzt welche Karte hat. Grund: Das Dorf (sogar die Tauscherin)
  stimmte gegen den Start-Werwolf, obwohl der Tausch offen genannt war. Wirkung noch nicht gemessen.
- Serie 6, alle Fixes seit Serie 5 zusammen (Fähigkeiten, konkrete erste Rede, NEUE_PARTEI,
  Persönlichkeit, TAUSCH_FOLGE), 20 Partien ab Seed 443803: 49,1 % (Zufall 25,9 %), Start-Werwölfe 43,5 %,
  Dorf gewinnt 11/20. Gegen Kontrolle gesichert (Fisher p ≈ 0,02), gegen Serie 4/5 noch nicht (p ≈ 0,5/0,2).
  Welcher Fix wie viel bringt, ist nicht trennbar. 9 Siege durch doppelte Rollenbehauptung (Seherin, Schlaflose).
  9 Niederlagen: 5× Nachtreihenfolge (Räuber hält beraubte Unruhestifterin für Lügnerin oder versteht
  nicht, dass er danach noch vertauscht wurde), 3× Kartenweg übersehen, 1× Herde.
  Bug: ERSTE_REDE/TAUSCH_FOLGE zwangen Spieler, die nachts Werwolf wurden, zur Wahrheit (Partie 9: Schlaflose
  sagt „ich bin jetzt Werwolf“). Serie 6 ist dadurch leicht geschönt.
- Fix danach: ERSTE_REDE erlaubt Lügnern ihre erfundene Geschichte, TAUSCH_FOLGE nur noch für Spieler, die nach
  ihrem Kartenwissen zum Dorf gehören. Der Räuber erfährt im Geheimwissen, wer nach ihm noch dran war und dass
  der Beraubte trotzdem mit seiner Startkarte handelt (_danach_hinweis in vollmondnacht/engine.py).
- Serie 7, mit diesen Fixes, 20 Partien ab Seed 443803: 50,9 % (Zufall 25,9 %), Start-Werwölfe 62,0 %
  (Serie 6: 43,5 %), Dorf gewinnt 10/20. Siege wie Serie 6, Stimmen gegen Start-Wölfe deutlich höher.
  27 von 29 Werwölfen behaupteten „Seherin“ (oft beide Wölfe zugleich), 12 davon starben. 10 Niederlagen:
  7× stirbt ein ehrlicher Spieler (3× die echte Seherin gegen Wolf-Seherinnen), 3× Kartenweg übersehen.
- Fix danach: Werwolf-Hinweis rät konkret zu einer Rolle aus der Mitte, warnt vor der Seherin und vor
  doppelten Behauptungen. Der einsame Wolf erfährt, ob niemand mit seiner gesehenen Karte begonnen hat.
  Macht die Wölfe stärker – Serie 8 ist damit eine neue Basis, nicht mit 6/7 vergleichbar.
- Serie 8, neue Basis mit diesem Fix, 20 Partien ab Seed 443803: 37,0 % (Zufall 25,9 %), Start-Werwölfe
  33,3 %, Dorf gewinnt 6/20. Werwolf-Behauptungen jetzt gestreut (Seherin 8/22, Schlaflose 8/22, Rest
  andere), nur 3 von 22 Wölfen sterben. 14 Niederlagen: 12× stirbt ein ehrlicher Spieler mit Info
  (7× Räuber/Unruhestifterin, „hat Chaos gestiftet“; 3× die echte Seherin gegen eine Wolf-Seherin;
  Betrunkener, Schlaflose), 2× Kartenweg übersehen. Das Wissen ist da, das Modell zieht aus
  Widersprüchen oft den falschen Schluss. Nebenwirkung von _danach_hinweis: Räuber, die sagen „meine Karte
  kann sich noch geändert haben“, wirken auf andere wie Ausreden (Partie 3).
  Nächster Schritt: Serie 9 mit stärkerem Modell, sonst unverändert.
- Serie 9, gpt-5.4-mini statt gemini-3.5-flash-lite (dazu LLM_TEMPERATUR=1, weil GPT-5-Modelle oft nur 1
  annehmen), sonst wie Serie 8, 20 Partien ab Seed 443803: 69,4 % (Zufall 25,6 %), Start-Werwölfe 49,1 %,
  Dorf gewinnt 14/20 (Serie 8: 6/20, Fisher p ≈ 0,03). Das Modell war der Flaschenhals, nicht die Prompts.
  Achtung: Auch die Werwölfe spielen mit dem stärkeren Modell – trotzdem gewinnt das Dorf deutlich öfter.
  Logs noch nicht im Detail ausgewertet.
- Serie 10, gpt-5.4 (groß), LLM_TEMPERATUR=1, aber andere Seeds (ab 263615, nicht 443803) – daher nur grob
  vergleichbar: 38,1 % (Zufall 21,5 %), Start-Werwölfe 48,7 %, Dorf gewinnt 7/20 (Serie 9: 14/20, p ≈ 0,06).
  Logs 16–20: Spiel deutlich hochwertiger. Werwölfe wählen unprüfbare Behauptungen (Unruhestifterin tauscht
  zwei Dorfbewohner), opfern den Partner, ein Räuber mit Werwolf-Karte verschweigt den Raub (NEUE_PARTEI
  wirkt). Das Dorf baut saubere Kartenketten (Partie 19). Niederlagen jetzt in echten 50:50-Lagen
  (zwei Schlaflose, zwei Seherinnen) oder bei verdecktem Raub – keine groben Regelfehler mehr.
Als Nächstes: offen – z. B. gemini-3.5-flash als zweites stärkeres Modell oder Agenten-Kern für die Simulation herauslösen.
