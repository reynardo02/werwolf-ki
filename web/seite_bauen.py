"""Baut die statische Seite für GitHub Pages in einen Ordner.

  python -m web.seite_bauen _site --pyodide pfad/zu/pyodide

Inhalt des Ordners:
  index.html, pyodide-backend.js   die Spielseite und ihr Server-Ersatz
  karten/                          die Kartenbilder
  werwolf-ki.zip                   unser Python-Code (core/, werwolf/, web/) für Pyodide
  pyodide/                         Python für den Browser (aus dem npm-Paket „pyodide“)

Pyodide liegt mit auf der Seite statt von einem CDN zu kommen: So ist die Version
fest und die Seite hängt von keinem fremden Server ab.
"""

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / "static"
PAKETE = ["core", "werwolf", "web"]
# Was Pyodide zum Starten braucht – mehr Pakete nutzen wir nicht, nur die Standardbibliothek.
PYODIDE_DATEIEN = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]


def code_packen(ziel: Path) -> list[str]:
    """Packt die Python-Dateien und Prompts in ein Zip. Gibt die Namen zurück."""
    namen = []
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as zip_datei:
        for paket in PAKETE:
            for datei in sorted((WURZEL / paket).rglob("*")):
                if "__pycache__" in datei.parts or "static" in datei.parts:
                    continue
                if datei.suffix in (".py", ".txt"):
                    name = datei.relative_to(WURZEL).as_posix()
                    zip_datei.write(datei, name)
                    namen.append(name)
    return namen


def _ersetzen(text: str, alt: str, neu: str) -> str:
    assert text.count(alt) == 1, f"{alt} nicht genau einmal gefunden"
    return text.replace(alt, neu)


def bauen(ziel: Path, pyodide: Path) -> None:
    fehlend = [d for d in PYODIDE_DATEIEN if not (pyodide / d).exists()]
    if fehlend:
        raise SystemExit(f"In {pyodide} fehlen: {', '.join(fehlend)}")
    if ziel.exists():
        shutil.rmtree(ziel)
    (ziel / "pyodide").mkdir(parents=True)
    shutil.copytree(STATIC / "karten", ziel / "karten")
    for datei in PYODIDE_DATEIEN:
        shutil.copy(pyodide / datei, ziel / "pyodide" / datei)
    namen = code_packen(ziel / "werwolf-ki.zip")

    # Versionsnummer gegen den Browser-Cache: Sonst lädt ein Browser nach einem Update evtl. neues
    # index.html, aber altes pyodide-backend.js oder alten Python-Code – das passt nicht zusammen.
    backend = (STATIC / "pyodide-backend.js").read_text(encoding="utf-8")
    version = hashlib.sha256(backend.encode() + (ziel / "werwolf-ki.zip").read_bytes()).hexdigest()[:12]
    (ziel / "pyodide-backend.js").write_text(
        _ersetzen(backend, '"./werwolf-ki.zip"', f'"./werwolf-ki.zip?v={version}"'), encoding="utf-8")
    seite = (STATIC / "index.html").read_text(encoding="utf-8")
    seite = _ersetzen(seite, '"./pyodide-backend.js"', f'"./pyodide-backend.js?v={version}"')
    # Markierung: Diese Fassung hat keinen Python-Server, also gleich Python im Browser laden.
    seite = _ersetzen(seite, '<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="werwolf-modus" content="browser">')
    (ziel / "index.html").write_text(seite, encoding="utf-8")
    # Ohne diese Datei würde GitHub Pages die Seite durch Jekyll schicken.
    (ziel / ".nojekyll").touch()
    print(f"Seite gebaut in {ziel}: {len(namen)} Python-/Prompt-Dateien, Pyodide aus {pyodide}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Statische Seite für GitHub Pages bauen")
    parser.add_argument("ziel", type=Path)
    parser.add_argument("--pyodide", type=Path, required=True, help="Ordner mit den Pyodide-Dateien")
    args = parser.parse_args()
    bauen(args.ziel, args.pyodide)


if __name__ == "__main__":
    main()
