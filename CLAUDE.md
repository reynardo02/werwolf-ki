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
  Anbieter-Auswahl im LLM-Zugang (OpenAI mit gpt-5.4 als Standard, Gemini, eigene); OpenAI schickt temperature=1.
Zusatz: Spielkarten im Browser – deine Karte liegt verdeckt (web/static/karten/rueckseite.jpg) und dreht sich per Klick um.
  Bilder heißen wie die Rolle, klein und ohne Umlaute (raeuber.jpg); fehlt eins, erscheint eine schlichte Karte mit dem Namen.
  Geheimwissen und Zug erscheinen erst, wenn du die Karte einmal angesehen hast.

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
  Spielqualität deutlich höher: Werwölfe behaupten meist „Schlaflose“ (13/26) oder Unprüfbares, decken sich
  gegenseitig (Partie 13: Wolf-Unruhestifterin „erklärt“ die doppelte Schlaflose des Partners), opfern den
  Partner (16), ein nachts zum Werwolf gewordener Spieler sagt die Wahrheit und lenkt damit auf den alten
  Wolf (8). Das Dorf baut saubere Kartenketten (14, 19). 13 Niederlagen: ~4× geschickte Wolf-Täuschung oder
  echtes 50:50 (zwei Schlaflose/Seherinnen), 3× Kartenweg übersehen, 3× ehrlicher Info-Spieler trotz
  lösbarer Lage, 2× kaum lösbar (Werwolf nur über den Betrunkenen am Tisch; Partie 5 ohne Werwolf am Tisch,
  das Dorf hätte niemanden töten dürfen). Die Siegquote misst ab hier nicht mehr nur das Dorf – die Wölfe
  werden mit dem Modell genauso besser.
- Regel-Fix nach eigener Browser-Partie (gpt-5.4, Partie 667996): Das Dorf meinte, wer die Schlaflose-Karte
  erst nachts bekommt, hätte am Ende etwas sehen müssen, hielt deshalb die ehrliche Unruhestifterin für eine
  Lügnerin und tötete die echte Seherin. Jetzt steht in den Regeln für alle: Nachts handelt jeder nur mit
  seiner Startkarte (vollmondnacht/prompts/system.txt). Bisher stand das nur im Dorf-Hinweis KARTENWEG.
- Regel-Fix nach eigener Browser-Partie (gpt-5.4, Partie 583495): Das Dorf meinte, die Seherin hätte bei Ben
  schon die Räuber-Karte sehen müssen, und tötete die ehrliche Räuberin. Jetzt steht in den Regeln: Wer nachts eine
  Karte ansieht, sieht den Stand in diesem Moment; die Rollenliste heißt ausdrücklich „in Nachtreihenfolge“.
- Fix nach eigener Browser-Partie (gpt-5.4, Partie 522974): Ein Wolf sah die Seherin in der Mitte, behauptete aber
  Schlaflose, obwohl die echte am Tisch saß – die Seherin-Warnung schreckte ab. Jetzt rät der Werwolf-Hinweis, genau die
  gesehene Mittelkarte zu behaupten, auch die Seherin. Macht die Wölfe stärker (neue Basis für spätere Serien).
- Serie 11, gpt-5.4, nach den drei Browser-Fixes, nur 10 Partien ab Seed 521937 (nicht vergleichbar): 50,9 %
  (Zufall 27,7 %), Start-Werwölfe 52,8 %, Dorf gewinnt 5/10. Niederlagen: ehrliche Unruhestifterin stirbt (2),
  Kartenweg übersehen (6, 9), kaum lösbar (7, Wolf nur über den Betrunkenen), 50:50 nach Redereihenfolge (10).
  Bug: Spieler verwechselten sich mit sich selbst (8: Ben „ich vote Ben“; 3: Anna über „Anna“). Ein Wolf sah den
  Betrunkenen in der Mitte und behauptete trotzdem Seherin (3) – vermutlich durch „auch die Seherin“ im Hinweis.
- Fix danach: Eigene Reden und Stimmen stehen im Verlauf als „Name (du)“ (_verlauf_zeile in
  vollmondnacht/llm_spieler.py), der Werwolf-Hinweis nennt ein Beispiel statt „auch die Seherin“.
- Serie 12, gpt-5.4, nach dem (du)-Fix, 20 Partien ab Seed 920519 (andere Seeds, nicht vergleichbar): 48,1 %
  (Zufall 25,9 %), Dorf gewinnt 9/20. Selbstverwechslung nicht mehr gesehen. 11 Niederlagen: 4× Kartenweg übersehen,
  obwohl der Tauscher ihn offen nannte (4, 5, 8, 18); 3× ehrlicher Getauschter verdächtig, weil er nur die Startkarte
  nennt (7, 11, 14); 2× 50:50 nach Redereihenfolge (6, 20); 1× ehrliche Seherin (19); 1× nur per Kartenzählen lösbar (2).
  Gesehene Mittelkarte behaupten: 2 von 6 einsamen Wölfen perfekt (11, 12), 3 verrieten dabei die Mittelkarte (1, 10, 18).
  Künftige Serien besser mit festen Seeds (z. B. --seed 263615), damit Unterschiede vergleichbar sind.
- Fix danach: Werwolf-Hinweis verbietet, die gesehene Mittelkarte zu erwähnen.
- Serie 13, gpt-5.4, mit diesem Fix, dieselben 20 Seeds wie Serie 12 (920519–920538): 44,4 % (Zufall 25,9 %),
  Dorf gewinnt 8/20. Gleiche Seeds machen Partien direkt vergleichbar: Das Ergebnis kippt trotzdem in 9 von 20 Seeds
  (Temperatur 1) – 20 Partien reichen nur für häufige Verhaltensweisen, nicht für ±1 Sieg. Fix wirkt: Keiner der 3 Wölfe
  aus 519/528/536 verrät mehr seine Mittelkarte. Nebenwirkung: Wölfe behaupten jetzt oft „Räuber“ (7 statt 2 Seeds),
  ehrliche Räuber sterben im 50:50 (6 statt 1). Bug: Wer nachts zum Werwolf wird, verrät es oft trotzdem in der
  ersten Rede („Ich war Schlaflose und jetzt bin ich Werwolf“; 4 von 6 Fällen in Serie 12+13).
- Fix danach: Wer nachts von Dorf auf eine andere Partei gewechselt ist, bekommt in jeder Rede die Warnung, das
  nicht zu verraten (NICHT_VERRATEN in vollmondnacht/llm_spieler.py). Messbar in den Seeds 920522, 920528, 920533.
- Serie 14, gpt-5.4, mit NICHT_VERRATEN, wieder Seeds 920519–920538: 54,6 % (Zufall 25,9 %), Start-Werwölfe 47,2 %,
  Dorf gewinnt 10/20 (Serie 13: 8/20 – im Rauschen). Fix wirkt in allen drei Fällen: In 920533 lügt die zum
  Werwolf gewordene Schlaflose („Ich war die Seherin“) statt sich zu verraten, in 920522 und 920537 lügen Räuberinnen,
  die einen Wolf geraubt haben („Unruhestifterin, X und Y vertauscht“) – in 522 so gut, dass das Dorf die ehrliche
  Schlaflose tötet. In 920528 wechselte diesmal niemand die Partei. Räuber-Muster bleibt: Wölfe behaupten „Räuber, Dorfbewohner gesehen“, und der
  echte Räuber stirbt im 50:50 (529, 534, 538). Keine groben Regelfehler mehr in den Logs – die Prompt-Phase ist
  damit vorerst abgeschlossen; die restlichen Niederlagen sind echte Spielfehler oder gute Wolf-Lügen.
- Regel-Fix nach eigener Browser-Partie (gpt-5.4-mini, Partie 696964): Die Unruhestifterin vertauschte nichts und sagte das
  offen – das bringt dem Dorf keine Information. Räuber und Unruhestifterin müssen jetzt handeln (kein Tool nichts_tun
  mehr, auch die Rollenbeschreibung sagt nicht mehr „darf“). Kartenverteilung und Mitte bleiben bei gleichem Seed gleich
  (LLM-Serien also weiter vergleichbar), nur Partien mit MockAgent laufen anders.
- Fix nach Serie 15, Seed 920520 (gpt-5.4): Kein Werwolf am Tisch, alle ehrlich. Das Dorf verrechnete sich beim Kartenweg
  (Anna habe jetzt den Betrunkenen – den hatte aber die Räuberin geraubt) und tötete Anna trotzdem, obwohl es ihr selbst
  eine Dorf-Karte zurechnete. Der Betrunkene, der einen Werwolf aus der Mitte gezogen hatte, blieb unbeachtet. KARTENWEG
  sagt jetzt: Wer laut Kartenkette eine Dorf-Karte hat, ist kein Werwolf; der Betrunkene kann ahnungslos Werwolf sein.
- Serie 15, gpt-5.4, mit Pflicht-Tausch und KARTENWEG-Fix, Seeds 920519–920538: 59,3 % (Zufall 25,9 %), Start-Werwölfe
  51,9 %, Dorf gewinnt 11/20 (Serie 14: 10/20 – im Rauschen). 920520 einmal gewonnen (Betrunkener mit Werwolf erkannt),
  einmal verloren. Ehrlicher Betrunkener als Sündenbock nur 1× (526, dort übersah das Dorf einen späten Rollenwechsel).
  9 Niederlagen: 4× Start- und Endkarte verwechselt (520, 529: Dorf tötet wissentlich eine Dorf-Karte, „er nennt nur seine
  Startkarte“; 527: vertauschte Schlaflose gilt als Lügnerin; 537: Räuberin hält den Beraubten für einen Lügner, obwohl ihr
  Blick ihn bestätigt), 2× Kartenweg übersehen (533, 536), 2× 50:50 nach Redereihenfolge (519, 538), 1× Betrunkener (526).
- Fix danach: Abstimmungs-Aufgabe fürs Dorf sagt „nicht auf jemanden, dem du selbst eine Dorf-Karte zurechnest“ (DORF_STIMME
  in vollmondnacht/llm_spieler.py). Neue Regel in system.txt: Beraubte und Vertauschte nennen zu Recht ihre Startkarte, der
  Blick des Räubers bestätigt sie; eine vorher vertauschte Schlaflose sieht die Karte, die sie bekommen hat.
- Serie 16, gpt-5.4, mit DORF_STIMME und der Beraubten-Regel, Seeds 920519–920538: 59,3 % (Zufall 25,9 %), Start-Werwölfe
  49,1 %, Dorf gewinnt 11/20 (Serie 15: 11/20). Regel-Fix wirkt: In 537 begründet Anna ihre Stimme damit, dass der vertauschte
  Ben zu Recht „Seherin“ sagt – Dorf gewinnt (Serie 15 verloren); 533, 536, 538 ebenfalls gekippt zum Sieg. 527/529 hatten
  andere Nächte, prüfen den Fix nicht. 9 Niederlagen: 3× später Startkarten-Wechsel übersehen („Dorfbewohner“, dann Seherin/
  Räuberin/Unruhestifterin; 519, 526, 532 – zweimal stirbt dafür der ehrliche Betrunkene), 1× „Dorf-Karte“ als Dorfbewohner-Karte
  gelesen (520), 1× Kartenweg übersehen (523), 2× Herde gegen stillen Dorfbewohner (528, 529), 2× starke Wolf-Täuschung (527, 534).
- Fix danach: DORF_STIMME definiert „Dorf-Karte“ (alles außer Werwolf, Günstling, Gerber), sagt, dass ein vertauschter Lügner
  seine Werwolf-Karte nicht mehr hat, und dass ein späterer Wechsel der Startkarte eine Lüge ist.
- Serie 17, gpt-5.4, mit erweitertem DORF_STIMME (A1/A2/C), Seeds 920519–920538: 51,9 % (Zufall 25,9 %), Start-Werwölfe
  48,1 %, Dorf gewinnt 10/20 (Serie 16: 11/20 – im Rauschen). C wirkt: In 519 und 529 begründen fast alle ihre Stimme mit dem
  Startkarten-Wechsel des Wolfs. 10 Niederlagen: 2× Lügner erkannt, aber seine Werwolf-Karte war weitergetauscht (526, 536 –
  Dario schreibt selbst „Ben hat meine Dorfkarte“ und stimmt trotzdem gegen Ben), 1× beraubte Seherin gilt als widerlegt, weil
  der Räuber bei ihr die Seherin sah (530, fast auch 522), 1× Wechsel als „Test“ entschuldigt (531), 2× Karten nicht gezählt
  (520: nur der Betrunkene konnte Wolf sein; 524: vier Dorfbewohner-Claims), 2× Herde ohne Widerspruch (528, 532),
  2× starke Wolf-Täuschung (527, 537).
- Fix danach: Lüge und Kartenweg in einem Satz in DORF_STIMME („Wer lügt, hatte wahrscheinlich die Werwolf-Karte – folge dann
  dieser Karte“, auch bei „Test“). Neue Regel in system.txt: Die Seherin ist vor dem Räuber dran, Rauben nimmt niemandem
  seine Nachtaktion. LUEGEN verlangt, bei der zuerst behaupteten Startkarte zu bleiben (macht die Wölfe stärker).
  Kartenzählen bewusst nicht als Hinweis (Serie 2).
- Serie 18, gpt-5.4, mit diesen Fixes, Seeds 920519–920538: 45,4 % (Zufall 25,9 %), Start-Werwölfe 44,4 %, Dorf gewinnt 8/20
  (Serie 17: 10/20 – im Rauschen, die Wölfe sind durch LUEGEN stärker). Wölfe bleiben fast immer bei ihrer Lüge (nur 532 wechselt
  noch, C erkennt es sofort); NICHT_VERRATEN wirkt (528, 533). Die Seherin-Regel greift nur teilweise (522 gewonnen, 530 verloren).
  12 Niederlagen: 4× 50:50 bei doppelter Behauptung, weil der Wolf hart bleibt (519, 528, 531, 537), 4× Herde gegen Ehrliche ohne
  Widerspruch, meist gegen Tauscher („bequem“, „Chaos“; 524, 526, 529, 536), 2× Regel zu Beraubten/Vertauschten nicht angewendet,
  obwohl sie im Prompt steht (527: vertauschte „Schlaflose“ sah angeblich ihre Startkarte; 530: beraubte Seherin), 1× Kartenweg
  (523), 1× perfekte Täuschung (534). Die Prompt-Phase ist damit abgeschlossen: Die restlichen Regelfehler betreffen Regeln, die
  schon zwei- bis dreimal im Prompt stehen, der Rest sind echte Spielentscheidungen.
Als Nächstes: offen – z. B. gemini-3.5-flash als zweites stärkeres Modell oder Agenten-Kern für die Simulation herauslösen.
