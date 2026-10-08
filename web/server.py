"""Ein kleiner Webserver mit Pythons eingebautem http.server – ganz ohne Framework.

Adressen (alle Antworten sind JSON, außer der Startseite):
  GET  /                      die Spielseite (static/index.html)
  GET  /karten/werwolf.jpg    Kartenbilder (static/karten/)
  GET  /api/optionen?spieler=7    Platz-Namen und Vollmondnacht-Szenarien für diese Spielerzahl
  POST /api/neu               neue Partie: {"regeln", "spieler", "llm", "szenario"}
  GET  /api/zustand?seit=0    Stand der Partie, nur Ereignisse ab Nummer `seit`
  POST /api/aktion            dein Zug: {"tool", "parameter"}

Der Server lauscht nur auf 127.0.0.1, ist also nur auf deinem eigenen Rechner erreichbar.
"""

import argparse
import json
import re
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from web.einstellungen import Fehler, einstellungen_pruefen, optionen
from web.sitzung import Sitzung

STARTSEITE = Path(__file__).parent / "static" / "index.html"
KARTEN = Path(__file__).parent / "static" / "karten"
# Nur einfache Dateinamen, damit niemand mit „../“ andere Dateien abrufen kann.
KARTEN_PFAD = re.compile(r"/karten/([a-z]+\.jpg)")
# Skripte für „Mitspieler per Link“: unsere Verbindungslogik und PeerJS (WebRTC).
SKRIPTE = {"/mehrspieler.js", "/peerjs.min.js"}


def sitzung_aus_anfrage(daten: dict[str, Any], ordner: Path | None = None) -> Sitzung:
    """Prüft die Einstellungen aus dem Formular und baut daraus eine Sitzung."""
    e = einstellungen_pruefen(daten)
    return Sitzung(regeln=e.regeln, spieler=e.spieler, llm=e.llm, menschen=e.menschen, szenario=e.szenario, namen=e.namen, ordner=ordner)


class Handler(BaseHTTPRequestHandler):
    server: "WerwolfServer"

    # --- Antworten ---------------------------------------------------------

    def _json(self, daten: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        inhalt = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def _koerper(self) -> dict[str, Any]:
        laenge = int(self.headers.get("Content-Length") or 0)
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
        except json.JSONDecodeError:
            raise Fehler("Ungültiges JSON") from None
        if not isinstance(daten, dict):
            raise Fehler("Erwartet wird ein JSON-Objekt")
        return daten

    # --- Routen ------------------------------------------------------------

    def do_GET(self) -> None:
        url = urlparse(self.path)
        abfrage = parse_qs(url.query)
        if url.path == "/":
            inhalt = STARTSEITE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)
        elif (treffer := KARTEN_PFAD.fullmatch(url.path)) and (KARTEN / treffer[1]).is_file():
            inhalt = (KARTEN / treffer[1]).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(inhalt)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(inhalt)
        elif url.path in SKRIPTE:
            inhalt = (STARTSEITE.parent / url.path[1:]).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)
        elif url.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)  # kein Symbol, aber auch kein Fehler
            self.end_headers()
        elif url.path == "/api/optionen":
            wert = abfrage.get("spieler", ["7"])[0]
            spieler = int(wert) if wert.isdigit() else 0
            self._json(optionen(spieler))
        elif url.path == "/api/zustand":
            sitzung = self.server.sitzung
            if sitzung is None:
                self._json({"laeuft": False})
                return
            wert = abfrage.get("seit", ["0"])[0]
            seit = int(wert) if wert.isdigit() else 0
            self._json({"laeuft": True, **sitzung.zustand(seit)})
        else:
            self._json({"fehler": "Nicht gefunden"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            daten = self._koerper()
            if self.path == "/api/neu":
                if self.server.sitzung:
                    self.server.sitzung.beenden()  # alte, wartende Partie freigeben
                self.server.sitzung = sitzung_aus_anfrage(daten, self.server.ordner)
                self.server.sitzung.starten()
                self._json({"ok": True})
            elif self.path == "/api/aktion":
                sitzung = self.server.sitzung
                if sitzung is None:
                    raise Fehler("Es läuft keine Partie")
                parameter = daten.get("parameter") or {}
                if not isinstance(parameter, dict):
                    raise Fehler("parameter muss ein Objekt sein")
                if not sitzung.antworten(str(daten.get("tool")), {k: str(v) for k, v in parameter.items()}):
                    self._json({"fehler": "Gerade ist niemand von dir gefragt"}, HTTPStatus.CONFLICT)
                    return
                self._json({"ok": True})
            else:
                self._json({"fehler": "Nicht gefunden"}, HTTPStatus.NOT_FOUND)
        except Fehler as fehler:
            self._json({"fehler": str(fehler)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Das Polling jede Sekunde würde sonst die Konsole fluten.


class WerwolfServer(ThreadingHTTPServer):
    def __init__(self, adresse: tuple[str, int], ordner: Path | None = None) -> None:
        super().__init__(adresse, Handler)
        self.sitzung: Sitzung | None = None
        self.ordner = ordner  # None: logs/ wie bei main.py


def main() -> None:
    parser = argparse.ArgumentParser(description="Werwolf im Browser spielen")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = parser.parse_args()

    server = WerwolfServer(("127.0.0.1", args.port))
    adresse = f"http://127.0.0.1:{server.server_port}/"
    print(f"Werwolf läuft auf {adresse}  (beenden mit Strg+C)")
    if not args.kein_browser:
        webbrowser.open(adresse)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")
    finally:
        if server.sitzung:
            server.sitzung.beenden()
        server.server_close()


if __name__ == "__main__":
    main()
