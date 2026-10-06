"""Statistiken über viele Vollmondnacht-Partien, berechnet aus den JSONL-Logs.

Wichtig: Gezählt wird mit den Endkarten. Wer nachts zum Werwolf getauscht wurde,
gilt als Werwolf – so entscheidet es auch die Siegbedingung. Zusätzlich zählen wir Stimmen
gegen Start-Werwölfe: Liegen die viel höher, erkennt das Dorf die Lügner, verfolgt aber
nicht, wohin ihre Karte getauscht wurde.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from werwolf.auswertung import _prozent, _zeile, quote
from werwolf.vollmondnacht.rollen import Rolle

WERWOLF = Rolle.WERWOLF.value


@dataclass
class VollmondPartie:
    gruppe: str
    startrollen: dict[str, str]
    endrollen: dict[str, str]
    gewinner: list[str] | None  # None: abgebrochen, []: niemand gewinnt
    tote: list[str]
    stimmen: dict[str, str]  # von -> ziel
    zufallsaktionen: int
    api: dict[str, Any] | None
    sieger: list[str] = field(default_factory=list)
    mensch: str | None = None  # Platz, an dem ein Mensch gespielt hat
    seed: int | None = None


def partie_aus_log(zeilen: list[dict[str, Any]]) -> VollmondPartie:
    kopf = zeilen[0]
    if kopf.get("art") != "partie" or kopf.get("regeln") != "vollmondnacht":
        raise ValueError("Kein Vollmondnacht-Log.")
    ende = next((z for z in zeilen if z["art"] in ("ergebnis", "abbruch")), {})
    llm = sum(1 for s in kopf["spieler"] if s["typ"] == "llm")
    modell = f"{kopf.get('modell')} ({llm}/{len(kopf['spieler'])} LLM)" if llm else "nur MockAgenten"
    if any(s["typ"] == "mensch" for s in kopf["spieler"]):
        modell += ", mit Mensch"  # getrennt halten, sonst verfälscht es die Experimente
    return VollmondPartie(
        gruppe=f"{kopf.get('szenario')}, {modell}",
        startrollen={s["name"]: s["rolle"] for s in kopf["spieler"]},
        endrollen=ende.get("endrollen", {}),
        gewinner=ende.get("gewinner") if ende.get("art") == "ergebnis" else None,
        tote=ende.get("tote", []),
        stimmen={z["daten"]["von"]: z["daten"]["ziel"] for z in zeilen if z["art"] == "stimme"},
        zufallsaktionen=sum(1 for z in zeilen if z["art"] == "zufallsaktion"),
        api=ende.get("api"),
        sieger=ende.get("sieger", []),
        mensch=next((s["name"] for s in kopf["spieler"] if s["typ"] == "mensch"), None),
        seed=kopf.get("seed"),
    )


def _partei(rolle: str) -> str:
    return next(r for r in Rolle if r.value == rolle).partei.value


@dataclass
class VollmondAuswertung:
    partien: int = 0
    abgebrochen: int = 0
    siege: Counter = field(default_factory=Counter)  # Partei -> Anzahl Partien
    niemand_gewinnt: int = 0
    niemand_stirbt: int = 0
    partien_mit_werwolf: int = 0
    werwolf_erwischt: int = 0
    dorf_stimmen: int = 0
    dorf_stimmen_werwolf: int = 0
    dorf_stimmen_startwerwolf: int = 0
    dorf_stimmen_erwartet_zufall: float = 0.0
    spieler: int = 0
    partei_gewechselt: int = 0
    zufallsaktionen: int = 0
    api_aufrufe: int = 0
    gruppen: dict[str, "VollmondAuswertung"] = field(default_factory=dict)

    @property
    def fertige(self) -> int:
        return self.partien - self.abgebrochen


def _zaehlen(a: VollmondAuswertung, p: VollmondPartie) -> None:
    a.partien += 1
    a.zufallsaktionen += p.zufallsaktionen
    if p.api:
        a.api_aufrufe += p.api.get("aufrufe", 0)
    if p.gewinner is None:
        a.abgebrochen += 1
        return
    a.siege.update(p.gewinner)
    a.niemand_gewinnt += not p.gewinner
    a.niemand_stirbt += not p.tote

    woelfe = {n for n, r in p.endrollen.items() if r == WERWOLF}
    startwoelfe = {n for n, r in p.startrollen.items() if r == WERWOLF}
    if woelfe:
        a.partien_mit_werwolf += 1
        a.werwolf_erwischt += bool(woelfe & set(p.tote))
    for n, start in p.startrollen.items():
        a.spieler += 1
        a.partei_gewechselt += _partei(start) != _partei(p.endrollen[n])
    for von, ziel in p.stimmen.items():
        if _partei(p.endrollen[von]) != "Dorfgemeinschaft":
            continue
        a.dorf_stimmen += 1
        a.dorf_stimmen_werwolf += ziel in woelfe
        a.dorf_stimmen_startwerwolf += ziel in startwoelfe
        # Zufällig zeigen: trifft einen Werwolf mit (Werwölfe) / (alle anderen).
        a.dorf_stimmen_erwartet_zufall += len(woelfe - {von}) / (len(p.endrollen) - 1)


def auswerten(partien: list[VollmondPartie]) -> VollmondAuswertung:
    gesamt = VollmondAuswertung()
    for p in partien:
        _zaehlen(gesamt, p)
        _zaehlen(gesamt.gruppen.setdefault(p.gruppe, VollmondAuswertung()), p)
    return gesamt


def bericht(a: VollmondAuswertung, titel: str) -> str:
    z = [titel, "-" * len(titel), _zeile("Partien", f"{a.partien} (davon {a.abgebrochen} abgebrochen)")]
    if not a.fertige:
        return "\n".join(z)
    for partei in ("Werwolfsrudel", "Dorfgemeinschaft", "Gerber"):
        z.append(_zeile(f"Sieg {partei}", _prozent(quote(a.siege[partei], a.fertige), f"({a.siege[partei]})")))
    z += [
        _zeile("Niemand gewinnt", _prozent(quote(a.niemand_gewinnt, a.fertige), f"({a.niemand_gewinnt})")),
        _zeile("Niemand stirbt", _prozent(quote(a.niemand_stirbt, a.fertige), f"({a.niemand_stirbt})")),
        "",
        "Dorf",
        _zeile("  erwischt einen Werwolf", _prozent(
            quote(a.werwolf_erwischt, a.partien_mit_werwolf),
            f"({a.werwolf_erwischt} von {a.partien_mit_werwolf} Partien mit Werwolf)")),
        _zeile("  Stimmen gegen Werwölfe", _prozent(
            quote(a.dorf_stimmen_werwolf, a.dorf_stimmen),
            f"(Zufall wäre {_prozent(quote(a.dorf_stimmen_erwartet_zufall, a.dorf_stimmen)).strip()})")),
        _zeile("  Stimmen gegen Start-Werwölfe", _prozent(
            quote(a.dorf_stimmen_startwerwolf, a.dorf_stimmen), "(Werwolf-Karte zu Spielbeginn)")),
        "",
        _zeile("Partei nachts gewechselt", _prozent(
            quote(a.partei_gewechselt, a.spieler), f"({a.partei_gewechselt} von {a.spieler} Spielern)")),
        _zeile("Zufallsaktionen pro Partie", f"{a.zufallsaktionen / a.partien:.1f}"),
    ]
    if a.api_aufrufe:
        z.append(_zeile("API-Aufrufe pro Partie", f"{a.api_aufrufe / a.partien:.0f}"))
    return "\n".join(z)


def mensch_bericht(partien: list[VollmondPartie]) -> str:
    """Deine Bilanz aus den Partien, in denen du selbst mitgespielt hast."""
    eigene = [p for p in partien if p.mensch and p.gewinner is not None]
    z = ["Deine Partien", "-------------", _zeile("Partien", str(len(eigene)))]
    if not eigene:
        return "\n".join(z)

    siege = sum(p.mensch in p.sieger for p in eigene)
    z.append(_zeile("Gewonnen", _prozent(quote(siege, len(eigene)), f"({siege})")))
    # Nach der Partei der Endkarte – die entscheidet, ob du gewinnst.
    for partei in ("Dorfgemeinschaft", "Werwolfsrudel"):
        als = [p for p in eigene if _partei(p.endrollen[p.mensch]) == partei]
        if als:
            gewonnen = sum(p.mensch in p.sieger for p in als)
            z.append(_zeile(f"  als {partei}", f"{gewonnen} von {len(als)} gewonnen"))

    # Deine Stimmen, wenn du am Ende im Dorf warst: Hast du einen Werwolf getroffen?
    # Nur Partien mit Werwolf am Tisch – liegen beide in der Mitte, gibt es nichts zu treffen.
    im_dorf = [
        p for p in eigene
        if _partei(p.endrollen[p.mensch]) == "Dorfgemeinschaft" and p.mensch in p.stimmen
        and WERWOLF in p.endrollen.values()
    ]
    treffer = sum(p.endrollen[p.stimmen[p.mensch]] == WERWOLF for p in im_dorf)
    if im_dorf:
        z.append(_zeile("Stimme traf Werwolf", f"{treffer} von {len(im_dorf)} (im Dorf, mit Werwolf am Tisch)"))

    # Wie sehr haben die anderen dich verdächtigt? Vergleich mit fairer Verteilung.
    gegen_dich = sum(sum(ziel == p.mensch for ziel in p.stimmen.values()) for p in eigene)
    fair = sum((len(p.stimmen) - 1) / (len(p.startrollen) - 1) for p in eigene)
    z.append(_zeile("Stimmen gegen dich", f"{gegen_dich} (bei Zufall etwa {fair:.1f})"))
    hingerichtet = sum(p.mensch in p.tote for p in eigene)
    z.append(_zeile("Du wurdest hingerichtet", f"{hingerichtet} von {len(eigene)}"))

    z.append("")
    for p in eigene:
        start, ende = p.startrollen[p.mensch], p.endrollen[p.mensch]
        karte = start if start == ende else f"{start} → {ende}"
        ergebnis = "gewonnen" if p.mensch in p.sieger else "verloren"
        stimme = p.stimmen.get(p.mensch, "–")
        z.append(f"  Seed {p.seed}: {p.mensch} ({karte}), Stimme gegen {stimme}, "
                 f"tot: {', '.join(p.tote) or 'niemand'} – {ergebnis}")
    return "\n".join(z)
