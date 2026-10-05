"""Die Werwolf-Engine: kennt die Regeln, fragt Agenten und prüft deren Aktionen."""

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from werwolf.roles import Rolle, Team, rollen_verteilen
from werwolf.schnittstelle import (
    ABSTIMMEN,
    NOTIZ_SCHREIBEN,
    OPFER_WAEHLEN,
    PRUEFEN,
    SPRECHEN,
    TEXT_TOOLS,
    ZIEL_TOOLS,
    Agent,
    Aktion,
    Ereignis,
    Phase,
    Zug,
)


@dataclass
class Spieler:
    name: str
    rolle: Rolle
    agent: Agent
    lebendig: bool = True
    geheimwissen: list[str] = field(default_factory=list)
    notizen: list[str] = field(default_factory=list)


@dataclass
class Ergebnis:
    gewinner: Team
    runden: int
    ueberlebende: list[str]


class Engine:
    def __init__(
        self,
        agenten: dict[str, Agent],
        rng: random.Random | None = None,
        rollen: dict[str, Rolle] | None = None,
        diskussionsrunden: int = 2,
        max_runden: int = 50,
        beobachter: Callable[[Ereignis], None] | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        # Feste Rollen sind praktisch für Tests, sonst wird zufällig verteilt.
        rollen = rollen or rollen_verteilen(list(agenten), self.rng)
        if set(rollen) != set(agenten):
            raise ValueError("Rollen und Agenten passen nicht zusammen.")

        self.spieler = {
            name: Spieler(name, rollen[name], agent) for name, agent in agenten.items()
        }
        self.diskussionsrunden = diskussionsrunden
        self.max_runden = max_runden
        self.beobachter = beobachter
        self.protokoll: list[Ereignis] = []
        self.runde = 0

        # Werwölfe kennen sich gegenseitig.
        woelfe = self._mit_rolle(Rolle.WERWOLF, nur_lebende=False)
        for wolf in woelfe:
            for anderer in woelfe:
                if anderer is not wolf:
                    wolf.geheimwissen.append(f"{anderer.name} ist Werwolf (Mitspieler).")

    # ------------------------------------------------------------------
    # Spielablauf
    # ------------------------------------------------------------------

    def spielen(self) -> Ergebnis:
        """Spielt eine komplette Partie und gibt den Gewinner zurück."""
        while True:
            self.runde += 1
            if self.runde > self.max_runden:
                # Kann nach den Regeln nicht passieren (jede Nacht stirbt jemand),
                # schützt aber vor Endlosschleifen bei künftigen Regeländerungen.
                raise RuntimeError(f"Partie nach {self.max_runden} Runden abgebrochen.")

            self._nacht()
            if (gewinner := self.sieger()) is not None:
                return self._ende(gewinner)

            self._diskussion()
            self._abstimmung()
            if (gewinner := self.sieger()) is not None:
                return self._ende(gewinner)

            self._rundenende()

    def sieger(self) -> Team | None:
        """Prüft die Siegbedingungen. None bedeutet: das Spiel läuft weiter."""
        woelfe = len(self._mit_rolle(Rolle.WERWOLF))
        dorf = len(self.lebende()) - woelfe
        if woelfe == 0:
            return Team.DORF
        if woelfe >= dorf:
            return Team.WERWOELFE
        return None

    def _nacht(self) -> None:
        self._melden(Phase.NACHT, f"Runde {self.runde} beginnt. Es wird Nacht.")

        # Werwölfe stimmen nacheinander ab, jeder sieht die Vorschläge der anderen.
        vorschlaege: list[str] = []
        opfer_kandidaten = [s.name for s in self._lebende_spieler() if s.rolle is not Rolle.WERWOLF]
        for wolf in self._mit_rolle(Rolle.WERWOLF):
            extra = [f"Vorschlag der Werwölfe heute Nacht: {v}" for v in vorschlaege]
            aktion = self._fragen(wolf, Phase.NACHT, OPFER_WAEHLEN, opfer_kandidaten, extra)
            ziel = aktion.parameter["ziel"]
            vorschlaege.append(ziel)
            self._melden(Phase.NACHT, f"{wolf.name} (Werwolf) wählt {ziel}.", oeffentlich=False)
            self._begruendung_melden(Phase.NACHT, wolf, aktion)

        # Mehrheit der Wolfsstimmen, bei Gleichstand entscheidet der Zufall.
        opfer = self._mehrheit(vorschlaege) or self.rng.choice(self._spitzenreiter(vorschlaege))

        for seherin in self._mit_rolle(Rolle.SEHERIN):
            kandidaten = [s.name for s in self._lebende_spieler() if s is not seherin]
            aktion = self._fragen(seherin, Phase.NACHT, PRUEFEN, kandidaten)
            ziel = self.spieler[aktion.parameter["ziel"]]
            seherin.geheimwissen.append(
                f"Runde {self.runde}: {ziel.name} ist {ziel.rolle.value}."
            )
            self._melden(
                Phase.NACHT, f"{seherin.name} (Seherin) prüft {ziel.name}.", oeffentlich=False
            )

        # Morgen: Opfer wird verkündet und seine Rolle aufgedeckt.
        self._toeten(Phase.MORGEN, opfer, "wurde in der Nacht von den Werwölfen getötet")

    def _diskussion(self) -> None:
        for _ in range(self.diskussionsrunden):
            for spieler in self._lebende_spieler():
                aktion = self._fragen(spieler, Phase.DISKUSSION, SPRECHEN)
                self._melden(Phase.DISKUSSION, f'{spieler.name}: "{aktion.parameter["text"]}"')

    def _abstimmung(self) -> None:
        stimmen: list[str] = []
        for spieler in self._lebende_spieler():
            kandidaten = [s.name for s in self._lebende_spieler() if s is not spieler]
            aktion = self._fragen(spieler, Phase.ABSTIMMUNG, ABSTIMMEN, kandidaten)
            ziel = aktion.parameter["ziel"]
            stimmen.append(ziel)
            self._melden(Phase.ABSTIMMUNG, f"{spieler.name} stimmt für {ziel}.")
            self._begruendung_melden(Phase.ABSTIMMUNG, spieler, aktion)

        # Nur eine eindeutige Mehrheit (meiste Stimmen) scheidet aus.
        verurteilt = self._mehrheit(stimmen)
        if verurteilt is None:
            self._melden(Phase.ABSTIMMUNG, "Gleichstand – niemand scheidet aus.")
        else:
            self._toeten(Phase.ABSTIMMUNG, verurteilt, "wurde vom Dorf hingerichtet")

    def _rundenende(self) -> None:
        for spieler in self._lebende_spieler():
            aktion = self._fragen(spieler, Phase.RUNDENENDE, NOTIZ_SCHREIBEN)
            spieler.notizen.append(f"Runde {self.runde}: {aktion.parameter['text']}")
            # Notizen sind privat, im Protokoll zeigen sie, was ein Spieler wirklich denkt.
            self._melden(
                Phase.RUNDENENDE, f"Notiz {spieler.name}: {aktion.parameter['text']}", oeffentlich=False
            )

    def _ende(self, gewinner: Team) -> Ergebnis:
        self._melden(Phase.SPIELENDE, f"Spielende: {gewinner.value} gewinnen!")
        return Ergebnis(gewinner, self.runde, [s.name for s in self._lebende_spieler()])

    # ------------------------------------------------------------------
    # Agenten fragen und Aktionen prüfen
    # ------------------------------------------------------------------

    def _fragen(
        self,
        spieler: Spieler,
        phase: Phase,
        tool: str,
        gueltige_ziele: list[str] | None = None,
        extra_wissen: list[str] | None = None,
    ) -> Aktion:
        """Fragt einen Agenten nach einer Aktion.

        Ungültige Aktionen werden abgelehnt, der Agent bekommt einen zweiten
        Versuch mit Hinweis. Ist auch der ungültig, wählt die Engine zufällig.
        """
        hinweis = None
        for _ in range(2):
            zug = Zug(
                ich=spieler.name,
                rolle=spieler.rolle,
                runde=self.runde,
                phase=phase,
                erlaubte_tools=[tool],
                lebende=self.lebende(),
                geheimwissen=spieler.geheimwissen + (extra_wissen or []),
                notizen=list(spieler.notizen),
                ereignisse=[e for e in self.protokoll if e.oeffentlich],
                hinweis=hinweis,
                ziele=list(gueltige_ziele or []),
            )
            aktion = spieler.agent.handeln(zug)
            hinweis = self._pruefen(aktion, tool, gueltige_ziele or [])
            if hinweis is None:
                return aktion
            self._melden(phase, f"Ungültige Aktion von {spieler.name}: {hinweis}", oeffentlich=False)

        self._melden(phase, f"{spieler.name} bekommt eine Zufallsaktion.", oeffentlich=False)
        return self._zufallsaktion(tool, gueltige_ziele or [])

    @staticmethod
    def _pruefen(aktion: Aktion, tool: str, gueltige_ziele: list[str]) -> str | None:
        """Gibt eine Fehlermeldung zurück oder None, wenn die Aktion gültig ist."""
        if aktion.tool != tool:
            return f"Tool '{aktion.tool}' ist jetzt nicht erlaubt, erwartet wird '{tool}'."
        if tool in ZIEL_TOOLS:
            ziel = aktion.parameter.get("ziel")
            if ziel not in gueltige_ziele:
                return f"'{ziel}' ist kein gültiges Ziel. Erlaubt: {', '.join(gueltige_ziele)}."
        if tool in TEXT_TOOLS:
            text = aktion.parameter.get("text")
            if not isinstance(text, str) or not text.strip():
                return "Der Parameter 'text' darf nicht leer sein."
        return None

    def _zufallsaktion(self, tool: str, gueltige_ziele: list[str]) -> Aktion:
        if tool in ZIEL_TOOLS:
            return Aktion(tool, {"ziel": self.rng.choice(gueltige_ziele)})
        return Aktion(tool, {"text": "(schweigt)"})

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    def lebende(self) -> list[str]:
        return [s.name for s in self._lebende_spieler()]

    def _lebende_spieler(self) -> list[Spieler]:
        return [s for s in self.spieler.values() if s.lebendig]

    def _mit_rolle(self, rolle: Rolle, nur_lebende: bool = True) -> list[Spieler]:
        return [
            s for s in self.spieler.values()
            if s.rolle is rolle and (s.lebendig or not nur_lebende)
        ]

    def _begruendung_melden(self, phase: Phase, spieler: Spieler, aktion: Aktion) -> None:
        if begruendung := aktion.parameter.get("begruendung"):
            self._melden(phase, f"Begründung {spieler.name}: {begruendung}", oeffentlich=False)

    def _toeten(self, phase: Phase, name: str, grund: str) -> None:
        spieler = self.spieler[name]
        spieler.lebendig = False
        self._melden(phase, f"{name} {grund}. {name} war {spieler.rolle.value}.")

    @staticmethod
    def _spitzenreiter(stimmen: list[str]) -> list[str]:
        """Alle Namen mit der höchsten Stimmenzahl."""
        zaehlung = Counter(stimmen)
        hoechste = max(zaehlung.values())
        return [name for name, anzahl in zaehlung.items() if anzahl == hoechste]

    def _mehrheit(self, stimmen: list[str]) -> str | None:
        """Der Name mit den meisten Stimmen, oder None bei Gleichstand."""
        spitze = self._spitzenreiter(stimmen)
        return spitze[0] if len(spitze) == 1 else None

    def _melden(self, phase: Phase, text: str, oeffentlich: bool = True) -> None:
        ereignis = Ereignis(self.runde, phase, text, oeffentlich)
        self.protokoll.append(ereignis)
        if self.beobachter:
            self.beobachter(ereignis)
