"""Statistiken über viele Partien, berechnet aus den JSONL-Logs.

Alles hier sind reine Funktionen auf bereits gelesenen Log-Zeilen,
deshalb lässt es sich ohne Dateien und ohne LLM testen.
"""

from dataclasses import dataclass, field
from typing import Any

WERWOLF = "Werwolf"
SEHERIN = "Seherin"


@dataclass
class Partie:
    """Die für die Statistik wichtigen Teile eines Logs."""

    modell: str | None
    rollen: dict[str, str]
    typen: dict[str, str]  # "llm", "mock" oder "mensch"
    ereignisse: list[dict[str, Any]]
    gewinner: str | None  # None: Partie wurde abgebrochen
    runden: int
    api: dict[str, Any] | None

    @property
    def gruppe(self) -> str:
        """Partien werden nach Modell und LLM-Anteil gruppiert."""
        llm = sum(1 for t in self.typen.values() if t == "llm")
        gruppe = f"{self.modell} ({llm}/{len(self.typen)} Spieler LLM)" if llm else "nur MockAgenten"
        # Partien mit Mensch getrennt halten, sonst verfälschen sie die Experimente.
        return gruppe + (", mit Mensch" if "mensch" in self.typen.values() else "")


def partie_aus_log(zeilen: list[dict[str, Any]]) -> Partie:
    if not zeilen or zeilen[0].get("art") != "partie":
        raise ValueError("Kein gültiges Partie-Log: erste Zeile fehlt.")
    kopf = zeilen[0]
    ende = next((z for z in zeilen if z["art"] in ("ergebnis", "abbruch")), None)
    ereignisse = [z for z in zeilen[1:] if "daten" in z]
    return Partie(
        modell=kopf.get("modell"),
        rollen={s["name"]: s["rolle"] for s in kopf["spieler"]},
        typen={s["name"]: s["typ"] for s in kopf["spieler"]},
        ereignisse=ereignisse,
        gewinner=ende.get("gewinner") if ende else None,
        runden=max((e["runde"] for e in ereignisse), default=0),
        api=ende.get("api") if ende else None,
    )


def quote(zaehler: float, nenner: float) -> float | None:
    return zaehler / nenner if nenner else None


@dataclass
class Auswertung:
    partien: int = 0
    abgebrochen: int = 0
    siege_werwoelfe: int = 0
    runden: int = 0
    # Seherin
    pruefungen: int = 0
    pruefungen_werwolf: int = 0
    seherin_gelegenheiten: int = 0  # Abstimmungen, bei denen sie einen lebenden Werwolf kannte
    seherin_wissen_genutzt: int = 0
    seherin_tot_in_nacht_1: int = 0
    # Dorf (Seherin + Dorfbewohner) beim Abstimmen
    dorf_stimmen: int = 0
    dorf_stimmen_werwolf: int = 0
    dorf_stimmen_erwartet_zufall: float = 0.0
    hinrichtungen: int = 0
    hinrichtungen_werwolf: int = 0
    gleichstaende: int = 0
    # Technik
    zufallsaktionen: int = 0
    api_aufrufe: int = 0
    api_fehler: int = 0
    gruppen: dict[str, "Auswertung"] = field(default_factory=dict)

    @property
    def fertige(self) -> int:
        return self.partien - self.abgebrochen


def partie_zaehlen(a: Auswertung, p: Partie) -> None:
    """Zählt eine Partie in die Auswertung `a` ein."""
    a.partien += 1
    if p.gewinner is None:
        a.abgebrochen += 1
    else:
        a.siege_werwoelfe += p.gewinner == "Werwölfe"
        a.runden += p.runden
    if p.api:
        a.api_aufrufe += p.api.get("aufrufe", 0)
        a.api_fehler += p.api.get("fehler", 0)

    # Die Ereignisse der Reihe nach durchgehen und mitverfolgen, wer lebt
    # und welche Werwölfe die Seherin schon kennt.
    lebende = set(p.rollen)
    bekannte_woelfe: set[str] = set()
    for e in p.ereignisse:
        art, d = e["art"], e["daten"]
        if art == "pruefung":
            a.pruefungen += 1
            if d["rolle"] == WERWOLF:
                a.pruefungen_werwolf += 1
                bekannte_woelfe.add(d["ziel"])
        elif art == "tod":
            lebende.discard(d["name"])
            if d["rolle"] == SEHERIN and d["ursache"] == "nacht" and e["runde"] == 1:
                a.seherin_tot_in_nacht_1 += 1
            if d["ursache"] == "abstimmung":
                a.hinrichtungen += 1
                a.hinrichtungen_werwolf += d["rolle"] == WERWOLF
        elif art == "gleichstand":
            a.gleichstaende += 1
        elif art == "zufallsaktion":
            a.zufallsaktionen += 1
        elif art == "stimme":
            von, ziel = d["von"], d["ziel"]
            if p.rollen[von] == WERWOLF:
                continue
            woelfe_lebend = sum(1 for n in lebende if p.rollen[n] == WERWOLF)
            a.dorf_stimmen += 1
            a.dorf_stimmen_werwolf += p.rollen[ziel] == WERWOLF
            # Ein zufälliger Wähler trifft einen Werwolf mit Wahrscheinlichkeit
            # (lebende Werwölfe) / (alle anderen Lebenden).
            a.dorf_stimmen_erwartet_zufall += woelfe_lebend / (len(lebende) - 1)
            if p.rollen[von] == SEHERIN and bekannte_woelfe & lebende:
                a.seherin_gelegenheiten += 1
                a.seherin_wissen_genutzt += ziel in bekannte_woelfe


def auswerten(partien: list[Partie]) -> Auswertung:
    gesamt = Auswertung()
    for p in partien:
        partie_zaehlen(gesamt, p)
        partie_zaehlen(gesamt.gruppen.setdefault(p.gruppe, Auswertung()), p)
    return gesamt


def _prozent(wert: float | None, details: str = "") -> str:
    text = "–" if wert is None else f"{wert:5.1%}"
    return f"{text}  {details}" if details else text


def _zeile(beschriftung: str, wert: str) -> str:
    return f"{beschriftung + ':':<32}{wert}"


def bericht(a: Auswertung, titel: str = "Gesamt") -> str:
    """Lesbarer Text-Bericht für eine Auswertung."""
    z = [titel, "-" * len(titel)]
    z.append(_zeile("Partien", f"{a.partien} (davon {a.abgebrochen} abgebrochen)"))
    if not a.fertige:
        return "\n".join(z)
    z += [
        _zeile("Siegquote Werwölfe", _prozent(
            quote(a.siege_werwoelfe, a.fertige), f"({a.siege_werwoelfe} von {a.fertige})")),
        _zeile("Runden im Schnitt", f"{a.runden / a.fertige:.1f}"),
        "",
        "Seherin",
        _zeile("  prüft einen Werwolf", _prozent(
            quote(a.pruefungen_werwolf, a.pruefungen),
            f"({a.pruefungen_werwolf} von {a.pruefungen} Prüfungen)")),
        _zeile("  stimmt gegen bekannten Wolf", _prozent(
            quote(a.seherin_wissen_genutzt, a.seherin_gelegenheiten),
            f"({a.seherin_wissen_genutzt} von {a.seherin_gelegenheiten} Gelegenheiten)")),
        _zeile("  stirbt in Nacht 1", _prozent(
            quote(a.seherin_tot_in_nacht_1, a.partien),
            f"({a.seherin_tot_in_nacht_1} von {a.partien} Partien)")),
        "",
        "Dorf beim Abstimmen",
        _zeile("  Stimmen gegen Werwölfe", _prozent(
            quote(a.dorf_stimmen_werwolf, a.dorf_stimmen),
            f"(Zufall wäre {_prozent(quote(a.dorf_stimmen_erwartet_zufall, a.dorf_stimmen)).strip()})")),
        _zeile("  Hinrichtung trifft Wolf", _prozent(
            quote(a.hinrichtungen_werwolf, a.hinrichtungen),
            f"({a.hinrichtungen_werwolf} von {a.hinrichtungen})")),
        _zeile("  Gleichstände", str(a.gleichstaende)),
        "",
        _zeile("Zufallsaktionen pro Partie", f"{a.zufallsaktionen / a.partien:.1f}"),
    ]
    if a.api_aufrufe:
        z.append(_zeile("API-Aufrufe pro Partie",
                        f"{a.api_aufrufe / a.partien:.0f} ({a.api_fehler} Fehler gesamt)"))
    return "\n".join(z)
