"""Engine für Vollmondnacht: eine Nacht, eine Diskussion, eine gleichzeitige Abstimmung.

Wichtig für das Verständnis:
- Nachts handelt jeder nach seiner Startkarte (so ruft der Spielleiter die Rollen auf).
- Karten werden nachts vertauscht. Für den Sieg zählt die Karte, die am Ende
  vor einem Spieler liegt – auch wenn er sie nicht kennt.
- Entscheidungen ohne echte Wahl (welche verdeckte Mittelkarte) trifft die Engine
  selbst per Zufall. Gefragt werden die Agenten nur, wo sie wirklich etwas entscheiden.
"""

import random
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from werwolf.schnittstelle import ABSTIMMEN, NACHT_WEITER, SPRECHEN, Agent, Aktion, Ereignis, Phase, Zug
from werwolf.vollmondnacht.rollen import NACHT_REIHENFOLGE, Partei, Rolle, gewinner_bestimmen

# Tools der Nacht (Abstimmen und Sprechen kommen aus der gemeinsamen Schnittstelle).
NACHAHMEN = "nachahmen"  # Doppelgängerin
SPIELER_ANSEHEN = "spieler_ansehen"  # Seherin
MITTE_ANSEHEN = "mitte_ansehen"  # Seherin: zwei Karten aus der Mitte
RAUBEN = "rauben"  # Räuber
VERTAUSCHEN = "vertauschen"  # Unruhestifterin

# Rollen, deren Aktion die Doppelgängerin sofort ausführt.
SOFORT_AKTIONEN = (Rolle.SEHERIN, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN, Rolle.BETRUNKENER)

Optionen = dict[str, dict[str, list[str]]]


@dataclass
class Spieler:
    name: str
    agent: Agent
    startrolle: Rolle
    wissen: list[str] = field(default_factory=list)
    bekannte_karte: Rolle | None = None  # zuletzt selbst gesehene eigene Karte


@dataclass
class VollmondErgebnis:
    gewinner: set[Partei]  # leer: niemand gewinnt
    sieger: list[str]  # Spieler, deren Endkarte zu einer Gewinnerpartei gehört
    tote: list[str]
    endrollen: dict[str, Rolle]


class VollmondEngine:
    def __init__(
        self,
        agenten: dict[str, Agent],
        karten: list[Rolle],
        rng: random.Random | None = None,
        verteilung: dict[str, Rolle] | None = None,
        mitte: list[Rolle] | None = None,
        diskussionsrunden: int = 2,
        beobachter: Callable[[Ereignis], None] | None = None,
        nacht_reihum: Collection[str] = (),
    ) -> None:
        """`nacht_reihum`: Plätze von Menschen, die sich ein Gerät teilen (siehe _nacht_reihum)."""
        self.rng = rng or random.Random()
        if len(karten) != len(agenten) + 3:
            raise ValueError("Es müssen genau 3 Karten mehr als Spieler im Spiel sein.")

        if verteilung is None:
            # Karten mischen, jeder bekommt eine, die letzten 3 liegen in der Mitte.
            gemischt = list(karten)
            self.rng.shuffle(gemischt)
            verteilung = dict(zip(agenten, gemischt))
            mitte = gemischt[len(agenten):]
        if set(verteilung) != set(agenten) or mitte is None or len(mitte) != 3:
            raise ValueError("Verteilung passt nicht zu den Spielern oder Mitte hat nicht 3 Karten.")

        self.spieler = {n: Spieler(n, a, verteilung[n]) for n, a in agenten.items()}
        self.karten: dict[str, Rolle] = dict(verteilung)  # Karte, die gerade vor jemandem liegt
        self.mitte: list[Rolle] = list(mitte)
        self.kopie: Rolle | None = None  # Rolle, die die Doppelgängerin nachahmt
        self.diskussionsrunden = diskussionsrunden
        self.beobachter = beobachter
        self.protokoll: list[Ereignis] = []
        self.nacht_reihum = set(nacht_reihum)
        self._vorab: dict[str, Aktion] = {}  # vorab eingesammelte Nachtentscheidungen
        self._erledigt: set[str] = set()  # Doppelgängerinnen, die schon reihum dran waren
        self.runde = 1  # Vollmondnacht hat nur eine Runde

    # ------------------------------------------------------------------
    # Spielablauf
    # ------------------------------------------------------------------

    def spielen(self) -> VollmondErgebnis:
        # Wie am Tisch die Rollenmarker: Alle wissen, welche Karten im Spiel sind.
        im_spiel = sorted(list(self.karten.values()) + self.mitte, key=lambda r: list(Rolle).index(r))
        self.im_spiel = set(im_spiel)
        self.im_spiel_anzahl = Counter(im_spiel)
        karten = ", ".join(r.value for r in im_spiel)
        # Der Spielleiter ruft die Rollen laut auf, also kennen alle die Reihenfolge.
        # Ohne sie lässt sich nicht prüfen, ob zwei Aussagen über Tausche zusammenpassen.
        reihenfolge = ", ".join(r.value for r in NACHT_REIHENFOLGE if r in im_spiel)
        self._melden(
            Phase.NACHT,
            f"Im Spiel sind diese {len(im_spiel)} Karten (3 davon liegen in der Mitte): {karten}. "
            f"Nachts sind die Rollen in dieser Reihenfolge dran: {reihenfolge}.",
            art="karten", daten={"karten": karten, "reihenfolge": reihenfolge},
        )
        self._melden(Phase.NACHT, "Es wird Nacht. Alle schließen die Augen.", art="runde")
        self._nacht()
        self._melden(Phase.DISKUSSION, "Der Tag bricht an. Wer sind die Werwölfe?", art="tag")
        self._diskussion()
        tote = self._abstimmung()
        return self._ende(tote)

    def rolle(self, karte: Rolle) -> Rolle:
        """Die Rolle einer Karte – die Doppelgängerin-Karte zählt als ihre Kopie."""
        if karte is Rolle.DOPPELGAENGERIN and self.kopie is not None:
            return self.kopie
        return karte

    def endrollen(self) -> dict[str, Rolle]:
        return {name: self.rolle(karte) for name, karte in self.karten.items()}

    # ------------------------------------------------------------------
    # Nacht
    # ------------------------------------------------------------------

    def _nacht(self) -> None:
        for s in self.spieler.values():
            s.wissen.append(f"Deine Karte zu Spielbeginn: {s.startrolle.value}.")
        if self.nacht_reihum:
            self._nacht_reihum()

        for dg in self._mit_startrolle(Rolle.DOPPELGAENGERIN):
            if dg.name not in self._erledigt:
                self._doppelgaengerin(dg)
        self._werwoelfe()
        for s in self._mit_startrolle(Rolle.GUENSTLING):
            self._guenstling(s)
        self._freimaurer()
        for s in self._mit_startrolle(Rolle.SEHERIN):
            self._seherin(s)
        for s in self._mit_startrolle(Rolle.RAEUBER):
            self._raeuber(s)
        for s in self._mit_startrolle(Rolle.UNRUHESTIFTERIN):
            self._unruhestifterin(s)
        for s in self._mit_startrolle(Rolle.BETRUNKENER):
            self._betrunkener(s)
        for s in self._mit_startrolle(Rolle.SCHLAFLOSE):
            self._schlaflose(s)
        # (9b) Die Doppel-Schlaflose wacht nach der echten Schlaflosen auf.
        if self.kopie is Rolle.SCHLAFLOSE:
            for dg in self._mit_startrolle(Rolle.DOPPELGAENGERIN):
                self._schlaflose(dg)

    def _nacht_reihum(self) -> None:
        """Menschen an einem geteilten Gerät: Jeder kommt genau einmal dran, in Sitzreihenfolge.

        Sonst verriete die Reihenfolge die Rolle (die Doppelgängerin ist zuerst dran) und wer
        übersprungen wird, hätte keine Nachtaktion. Das geht ohne Regeländerung, weil nachts
        alle blind wählen: Wen Seherin, Räuber oder Unruhestifterin nehmen, hängt nicht davon ab,
        was andere vorher getan haben. Die Wahl wird hier eingesammelt und später in der
        Nachtreihenfolge ausgeführt. Die Doppelgängerin handelt gleich ganz – sie ist sowieso
        als Erste dran, also hat sich bis dahin nichts geändert.
        """
        for s in self.spieler.values():
            if s.name not in self.nacht_reihum:
                continue
            if s.startrolle is Rolle.DOPPELGAENGERIN:
                self._doppelgaengerin(s)
                self._erledigt.add(s.name)
            elif s.startrolle in NACHT_OPTIONEN:
                self._vorab[s.name] = self._fragen(s, Phase.NACHT, NACHT_OPTIONEN[s.startrolle](self, s))
            else:
                self._fragen(s, Phase.NACHT, {NACHT_WEITER: {}})

    def _nachtfrage(self, spieler: Spieler, optionen: Optionen) -> Aktion:
        """Die Nachtentscheidung: vorab eingesammelt (_nacht_reihum) oder jetzt gefragt."""
        return self._vorab.pop(spieler.name, None) or self._fragen(spieler, Phase.NACHT, optionen)

    def _optionen_seherin(self, s: Spieler) -> Optionen:
        return {SPIELER_ANSEHEN: {"ziel": self._andere(s)}, MITTE_ANSEHEN: {}}

    def _optionen_raeuber(self, s: Spieler) -> Optionen:
        # Kein „nichts tun“: Eine Unruhestifterin, die nichts vertauscht hatte, wirkte in einer
        # eigenen Partie (696964) nur verdächtig und brachte dem Dorf keine Information.
        return {RAUBEN: {"ziel": self._andere(s)}}

    def _optionen_unruhestifterin(self, s: Spieler) -> Optionen:
        andere = self._andere(s)
        return {VERTAUSCHEN: {"ziel1": andere, "ziel2": andere}}

    def _doppelgaengerin(self, dg: Spieler) -> None:
        aktion = self._fragen(dg, Phase.NACHT, {NACHAHMEN: {"ziel": self._andere(dg)}})
        ziel = aktion.parameter["ziel"]
        self.kopie = self.karten[ziel]
        dg.wissen.append(
            f"Du hast die Karte von {ziel} angesehen: {self.kopie.value}. Du bist jetzt "
            f"{self.kopie.value} und gehörst zur Partei {self.kopie.partei.value}."
        )
        self._nachtaktion(dg, NACHAHMEN, ziel=ziel, ergebnis=self.kopie.value)
        if self.kopie in SOFORT_AKTIONEN:
            {
                Rolle.SEHERIN: self._seherin,
                Rolle.RAEUBER: self._raeuber,
                Rolle.UNRUHESTIFTERIN: self._unruhestifterin,
                Rolle.BETRUNKENER: self._betrunkener,
            }[self.kopie](dg)
        elif self.kopie is Rolle.GUENSTLING:
            self._guenstling(dg)

    def _werwoelfe(self) -> None:
        woelfe = self._gruppe(Rolle.WERWOLF)
        if len(woelfe) >= 2:
            namen = ", ".join(w.name for w in woelfe)
            for w in woelfe:
                w.wissen.append(f"Die Werwölfe sind: {namen}.")
            self._nachtaktion(None, "werwoelfe_erkennen", ergebnis=namen)
        elif len(woelfe) == 1:
            # Einsamer Wolf: darf eine Karte aus der Mitte ansehen.
            wolf, nummer = woelfe[0], self.rng.randrange(3)
            karte = self.mitte[nummer]
            wissen = (
                f"Du bist der einzige Werwolf unter den Spielern. "
                f"Karte {nummer + 1} aus der Mitte ist: {karte.value}."
            )
            # Gibt es die Karte nur einmal, folgt daraus: Niemand hat mit ihr begonnen.
            # Genau so eine Rolle empfiehlt die Anleitung dem Werwolf zum Behaupten.
            if karte is not Rolle.WERWOLF and self.im_spiel_anzahl[karte] == 1:
                wissen += f" Also hatte kein Mitspieler zu Beginn die Karte {karte.value}."
            wolf.wissen.append(wissen)
            self._nachtaktion(wolf, "mitte_ansehen", karte=str(nummer + 1), ergebnis=karte.value)

    def _guenstling(self, guenstling: Spieler) -> None:
        woelfe = [w.name for w in self._gruppe(Rolle.WERWOLF)]
        if woelfe:
            guenstling.wissen.append(f"Die Werwölfe sind: {', '.join(woelfe)}. Sie kennen dich nicht.")
        else:
            guenstling.wissen.append("Kein Mitspieler ist Werwolf – die Werwolf-Karten liegen in der Mitte.")
        self._nachtaktion(guenstling, "werwoelfe_sehen", ergebnis=", ".join(woelfe) or "keine")

    def _freimaurer(self) -> None:
        freimaurer = self._gruppe(Rolle.FREIMAURER)
        for f in freimaurer:
            andere = [x.name for x in freimaurer if x is not f]
            if andere:
                f.wissen.append(f"Freimaurer sind außer dir: {', '.join(andere)}.")
            else:
                f.wissen.append("Du bist der einzige Freimaurer, die andere Karte liegt in der Mitte.")
        if freimaurer:
            self._nachtaktion(None, "freimaurer_erkennen", ergebnis=", ".join(f.name for f in freimaurer))

    def _seherin(self, seherin: Spieler) -> None:
        aktion = self._nachtfrage(seherin, self._optionen_seherin(seherin))
        if aktion.tool == SPIELER_ANSEHEN:
            ziel = aktion.parameter["ziel"]
            karte = self.karten[ziel]
            seherin.wissen.append(f"Du hast die Karte von {ziel} angesehen: {karte.value}.")
            self._nachtaktion(seherin, SPIELER_ANSEHEN, ziel=ziel, ergebnis=karte.value)
        else:
            nummern = sorted(self.rng.sample(range(3), 2))
            gesehen = [f"Karte {n + 1}: {self.mitte[n].value}" for n in nummern]
            seherin.wissen.append(f"Du hast zwei Karten aus der Mitte angesehen: {', '.join(gesehen)}.")
            self._nachtaktion(seherin, MITTE_ANSEHEN, ergebnis=", ".join(gesehen))

    def _raeuber(self, raeuber: Spieler) -> None:
        aktion = self._nachtfrage(raeuber, self._optionen_raeuber(raeuber))
        ziel = aktion.parameter["ziel"]
        self._tauschen(raeuber.name, ziel)
        neu = self.karten[raeuber.name]
        raeuber.bekannte_karte = neu
        raeuber.wissen.append(
            f"Du hast deine Karte mit {ziel} getauscht. Deine neue Karte: {neu.value}. "
            f"{ziel} hat jetzt deine alte Karte." + self._danach_hinweis(raeuber, ziel)
        )
        self._nachtaktion(raeuber, RAUBEN, ziel=ziel, ergebnis=neu.value)

    def _danach_hinweis(self, raeuber: Spieler, ziel: str) -> str:
        """Was nach dem Raub noch passieren kann – Regelwissen zur eigenen Nacht.

        In Serie 6 hielten Räuber ehrliche Mitspieler für Lügner: Die beraubte
        Unruhestifterin tauschte danach noch (sie handelt mit ihrer Startkarte), oder
        der Räuber wurde selbst noch vertauscht. Beides folgt aus der Reihenfolge.
        """
        position = NACHT_REIHENFOLGE.index(raeuber.startrolle)
        danach = [r for r in NACHT_REIHENFOLGE[position + 1:] if r in self.im_spiel]
        if not danach:
            return ""
        text = (
            f" Nach dir waren noch dran: {', '.join(r.value for r in danach)}. "
            "Deine neue Karte kann danach also noch vertauscht worden sein."
        )
        beraubt = self.spieler[ziel].startrolle
        if beraubt in danach:
            text += (
                f" {ziel} ist trotzdem noch als {beraubt.value} aufgewacht und hat gehandelt – "
                "nachts handelt jeder mit seiner Startkarte."
            )
        return text

    def _unruhestifterin(self, us: Spieler) -> None:
        aktion = self._nachtfrage(us, self._optionen_unruhestifterin(us))
        a, b = aktion.parameter["ziel1"], aktion.parameter["ziel2"]
        self._tauschen(a, b)
        us.wissen.append(f"Du hast die Karten von {a} und {b} vertauscht, ohne sie anzusehen.")
        self._nachtaktion(us, VERTAUSCHEN, ziel1=a, ziel2=b)

    def _betrunkener(self, betrunkener: Spieler) -> None:
        nummer = self.rng.randrange(3)
        self.karten[betrunkener.name], self.mitte[nummer] = self.mitte[nummer], self.karten[betrunkener.name]
        betrunkener.wissen.append(
            f"Du hast deine Karte mit Karte {nummer + 1} aus der Mitte getauscht, ohne sie anzusehen."
        )
        self._nachtaktion(betrunkener, "mitte_tauschen", karte=str(nummer + 1))

    def _schlaflose(self, schlaflose: Spieler) -> None:
        karte = self.karten[schlaflose.name]
        schlaflose.bekannte_karte = karte
        schlaflose.wissen.append(f"Am Ende der Nacht liegt diese Karte vor dir: {karte.value}.")
        self._nachtaktion(schlaflose, "eigene_karte_ansehen", ergebnis=karte.value)

    # ------------------------------------------------------------------
    # Tag
    # ------------------------------------------------------------------

    def _diskussion(self) -> None:
        for _ in range(self.diskussionsrunden):
            for s in self.spieler.values():
                aktion = self._fragen(s, Phase.DISKUSSION, {SPRECHEN: {}})
                text = aktion.parameter["text"]
                self._melden(
                    Phase.DISKUSSION, f'{s.name}: "{text}"', art="rede",
                    daten={"spieler": s.name, "text": text},
                )

    def _abstimmung(self) -> list[str]:
        # Gleichzeitig: Erst alle Stimmen einsammeln, dann verkünden. So sieht
        # niemand, wie die anderen gestimmt haben.
        stimmen: dict[str, Aktion] = {}
        for s in self.spieler.values():
            stimmen[s.name] = self._fragen(s, Phase.ABSTIMMUNG, {ABSTIMMEN: {"ziel": self._andere(s)}})
        self._melden(Phase.ABSTIMMUNG, "Auf drei zeigen alle gleichzeitig auf einen Mitspieler!", art="info")
        for name, aktion in stimmen.items():
            ziel = aktion.parameter["ziel"]
            self._melden(
                Phase.ABSTIMMUNG, f"{name} zeigt auf {ziel}.", art="stimme", daten={"von": name, "ziel": ziel}
            )
            if begruendung := aktion.parameter.get("begruendung"):
                self._melden(
                    Phase.ABSTIMMUNG, f"Begründung {name}: {begruendung}", oeffentlich=False,
                    art="begruendung", daten={"spieler": name, "text": str(begruendung)},
                )

        zaehlung = Counter(a.parameter["ziel"] for a in stimmen.values())
        hoechste = max(zaehlung.values())
        if hoechste == 1:
            # Jeder hat genau 1 Stimme: niemand stirbt.
            self._melden(Phase.ABSTIMMUNG, "Jeder hat genau eine Stimme – niemand stirbt.", art="gleichstand")
            return []

        # Wer die meisten Stimmen hat, stirbt – bei Gleichstand alle Beteiligten.
        tote = sorted(n for n, z in zaehlung.items() if z == hoechste)
        for name in tote:
            self._tod(name, "abstimmung")
        # Jäger: Wer stirbt und am Ende Jäger ist, reißt sein Ziel mit in den Tod.
        neu = list(tote)
        while neu:
            jaeger = [n for n in neu if self.rolle(self.karten[n]) is Rolle.JAEGER]
            neu = []
            for j in jaeger:
                ziel = stimmen[j].parameter["ziel"]
                if ziel not in tote:
                    tote.append(ziel)
                    neu.append(ziel)
                    self._tod(ziel, "jaeger", jaeger=j)
        return tote

    def _ende(self, tote: list[str]) -> VollmondErgebnis:
        endrollen = self.endrollen()
        for name, s in self.spieler.items():
            self._melden(
                Phase.SPIELENDE,
                f"{name}: Startkarte {s.startrolle.value}, Endkarte {endrollen[name].value}.",
                art="aufdecken",
                daten={"name": name, "startrolle": s.startrolle.value, "endrolle": endrollen[name].value},
            )
        mitte = ", ".join(k.value for k in self.mitte)
        self._melden(Phase.SPIELENDE, f"In der Mitte liegen: {mitte}.", art="mitte", daten={"karten": mitte})

        gewinner = gewinner_bestimmen(endrollen, set(tote))
        sieger = [n for n, r in endrollen.items() if r.partei in gewinner]
        text = " und ".join(sorted(p.value for p in gewinner)) + " gewinnt" if gewinner else "Niemand gewinnt"
        self._melden(
            Phase.SPIELENDE,
            f"Spielende: {text}! Sieger: {', '.join(sieger) or 'niemand'}.",
            art="spielende",
            daten={"gewinner": ", ".join(sorted(p.value for p in gewinner)), "sieger": ", ".join(sieger)},
        )
        return VollmondErgebnis(gewinner, sieger, tote, endrollen)

    # ------------------------------------------------------------------
    # Agenten fragen und Aktionen prüfen
    # ------------------------------------------------------------------

    def _fragen(self, spieler: Spieler, phase: Phase, optionen: Optionen) -> Aktion:
        """Fragt einen Agenten. Ungültig: zweiter Versuch mit Hinweis, dann Zufallsaktion."""
        hinweis = None
        for _ in range(2):
            zug = Zug(
                ich=spieler.name,
                rolle=spieler.startrolle,
                runde=self.runde,
                phase=phase,
                erlaubte_tools=list(optionen),
                lebende=list(self.spieler),
                geheimwissen=list(spieler.wissen),
                notizen=[],
                ereignisse=[e for e in self.protokoll if e.oeffentlich],
                hinweis=hinweis,
                # Freitext-Tools haben keine festen Werte, alle anderen schon.
                optionen={t: p for t, p in optionen.items() if t != SPRECHEN},
                bekannte_karte=spieler.bekannte_karte,
            )
            aktion = spieler.agent.handeln(zug)
            hinweis = self._pruefen(aktion, optionen)
            if hinweis is None:
                return aktion
            self._melden(
                phase, f"Ungültige Aktion von {spieler.name}: {hinweis}", oeffentlich=False,
                art="ungueltig", daten={"spieler": spieler.name, "fehler": hinweis},
            )
        aktion = self._zufallsaktion(optionen)
        self._melden(
            phase, f"{spieler.name} bekommt eine Zufallsaktion.", oeffentlich=False,
            art="zufallsaktion", daten={"spieler": spieler.name, "tool": aktion.tool},
        )
        return aktion

    @staticmethod
    def _pruefen(aktion: Aktion, optionen: Optionen) -> str | None:
        if aktion.tool not in optionen:
            return f"Tool '{aktion.tool}' ist jetzt nicht erlaubt. Erlaubt: {', '.join(optionen)}."
        for parameter, werte in optionen[aktion.tool].items():
            wert = aktion.parameter.get(parameter)
            if wert not in werte:
                return f"'{wert}' ist für '{parameter}' nicht gültig. Erlaubt: {', '.join(werte)}."
        if aktion.tool == VERTAUSCHEN and aktion.parameter["ziel1"] == aktion.parameter["ziel2"]:
            return "Du musst zwei verschiedene Spieler wählen."
        if aktion.tool == SPRECHEN:
            text = aktion.parameter.get("text")
            if not isinstance(text, str) or not text.strip():
                return "Der Parameter 'text' darf nicht leer sein."
        return None

    def _zufallsaktion(self, optionen: Optionen) -> Aktion:
        tool = next(iter(optionen))
        if tool == SPRECHEN:
            return Aktion(tool, {"text": "(schweigt)"})
        if tool == VERTAUSCHEN:
            a, b = self.rng.sample(optionen[tool]["ziel1"], 2)
            return Aktion(tool, {"ziel1": a, "ziel2": b})
        return Aktion(tool, {p: self.rng.choice(w) for p, w in optionen[tool].items()})

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    def _mit_startrolle(self, rolle: Rolle) -> list[Spieler]:
        return [s for s in self.spieler.values() if s.startrolle is rolle]

    def _gruppe(self, rolle: Rolle) -> list[Spieler]:
        """Wer nachts als diese Rolle aufwacht – inklusive nachahmender Doppelgängerin."""
        gruppe = self._mit_startrolle(rolle)
        if self.kopie is rolle:
            gruppe += self._mit_startrolle(Rolle.DOPPELGAENGERIN)
        return gruppe

    def _andere(self, spieler: Spieler) -> list[str]:
        return [n for n in self.spieler if n != spieler.name]

    def _tauschen(self, a: str, b: str) -> None:
        self.karten[a], self.karten[b] = self.karten[b], self.karten[a]

    def _tod(self, name: str, ursache: str, **daten: str) -> None:
        rolle = self.rolle(self.karten[name])
        grund = "wird vom Dorf hingerichtet" if ursache == "abstimmung" else (
            f"wird vom Jäger {daten.get('jaeger')} mit in den Tod gerissen"
        )
        self._melden(
            Phase.ABSTIMMUNG, f"{name} {grund}. {name} war {rolle.value}.", art="tod",
            daten={"name": name, "rolle": rolle.value, "ursache": ursache, **daten},
        )

    def _nachtaktion(self, spieler: Spieler | None, aktion: str, **daten: str) -> None:
        """Geheimes Protokoll der Nacht: Wer hat was getan und gesehen?"""
        wer = f"{spieler.name} ({spieler.startrolle.value})" if spieler else "Spielleiter"
        details = ", ".join(f"{k}={v}" for k, v in daten.items())
        self._melden(
            Phase.NACHT, f"{wer}: {aktion}" + (f" ({details})" if details else ""), oeffentlich=False,
            art="nacht_aktion",
            daten={"spieler": spieler.name if spieler else "", "rolle": spieler.startrolle.value if spieler else "",
                   "aktion": aktion, **daten},
        )

    def _melden(
        self, phase: Phase, text: str, oeffentlich: bool = True, art: str = "info",
        daten: dict[str, str] | None = None,
    ) -> None:
        ereignis = Ereignis(self.runde, phase, text, oeffentlich, art, daten or {})
        self.protokoll.append(ereignis)
        if self.beobachter:
            self.beobachter(ereignis)


# Startrollen, die nachts etwas wählen (ohne Doppelgängerin, die gleich ganz handelt).
NACHT_OPTIONEN: dict[Rolle, Callable[[VollmondEngine, Spieler], Optionen]] = {
    Rolle.SEHERIN: VollmondEngine._optionen_seherin,
    Rolle.RAEUBER: VollmondEngine._optionen_raeuber,
    Rolle.UNRUHESTIFTERIN: VollmondEngine._optionen_unruhestifterin,
}
