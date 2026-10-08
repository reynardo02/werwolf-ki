// Mitspieler per Link: Ein Browser ist Gastgeber und spielt die Partie (mit seinem API-Key),
// Gäste verbinden sich über einen Link mit ihm.
//
// - Der Gastgeber schickt jedem Gast nur, was dieser sehen darf: alles Öffentliche, dazu
//   Karte, Wissen und Frage seines eigenen Platzes. Züge eines Gastes nimmt er nur an,
//   wenn gerade genau dieser Platz gefragt ist.
// - Für die Seite ist ein Gast ein ganz normales „Backend“ (wie pyodide-backend.js):
//   Sie fragt /api/zustand ab und schickt /api/aktion – nur kommt beides vom Gastgeber.
//
// Verbindung: WebRTC über PeerJS (peerjs.min.js liegt auf der Seite, MIT-Lizenz). Der
// PeerJS-Vermittlungsserver hilft nur beim Verbindungsaufbau, danach reden die Browser
// direkt miteinander. Für Tests ohne Internet: ?verbindung=lokal nutzt BroadcastChannel
// (zwei Fenster im selben Browser).

const PRAEFIX = "werwolf-ki-";
// Herzschlag: WebRTC meldet nicht zuverlässig, wenn die Gegenseite den Tab schließt oder neu lädt.
// Beide Seiten senden deshalb regelmäßig ein Lebenszeichen; bleibt es aus, gilt die Verbindung als weg.
const PULS_MS = 4000, STILLE_MS = 12000;

function zufall(laenge) {
  const zeichen = "abcdefghijkmnopqrstuvwxyz23456789";
  return Array.from(crypto.getRandomValues(new Uint8Array(laenge)), (z) => zeichen[z % zeichen.length]).join("");
}

export const neuerRaum = () => PRAEFIX + zufall(12);
export const neuesZeichen = () => zufall(16);

// --- Verbindungen --------------------------------------------------------------
// Beide Arten bieten dasselbe: Der Gastgeber öffnet einen Raum und bekommt für jeden Gast
// einen Kanal, ein Gast verbindet sich mit einem Raum. Ein Kanal kann senden(daten),
// beiNachricht(fn) und beiEnde(fn).

const lokal = () => new URLSearchParams(location.search).get("verbindung") === "lokal";

let peerGeladen = null;
function peerLaden() {
  peerGeladen ||= new Promise((fertig, fehler) => {
    if (window.Peer) return fertig(window.Peer);
    const skript = Object.assign(document.createElement("script"), { src: new URL("./peerjs.min.js", import.meta.url).href });
    skript.onload = () => fertig(window.Peer);
    skript.onerror = () => fehler(new Error("PeerJS konnte nicht geladen werden"));
    document.head.append(skript);
  });
  return peerGeladen;
}

// Große Nachrichten in Stücke teilen: WebRTC-Datenkanäle vertragen je nach Browser nur 16–64 KB pro
// Nachricht (Safari eher wenig), und PeerJS teilt im JSON-Modus nicht selbst. Der Endstand mit
// Protokoll und Log ist mit echten LLM-Reden größer – er kam beim Gast nie an (eigene Partie).
// 8000 Zeichen sind auch mit Umlauten und Emojis sicher unter 32 KB.
const TEIL = 8000;

export function zerlegen(daten, nummer) {
  const text = JSON.stringify(daten);
  const anzahl = Math.max(1, Math.ceil(text.length / TEIL));
  return Array.from({ length: anzahl }, (_, i) => ({ stueck: nummer, i, von: anzahl, text: text.slice(i * TEIL, (i + 1) * TEIL) }));
}

// Gibt eine Funktion zurück, die Stücke annimmt und die ganze Nachricht liefert, sobald sie komplett ist.
export function zusammensetzer() {
  const offen = new Map();  // Nummer -> bisher angekommene Teile
  return (teil) => {
    if (!teil || typeof teil.text !== "string" || !(teil.von >= 1) || teil.von > 1000) return undefined;
    if (teil.von === 1) return JSON.parse(teil.text);
    const teile = offen.get(teil.stueck) || [];
    teile[teil.i] = teil.text;
    if (teile.filter((t) => t !== undefined).length < teil.von) { offen.set(teil.stueck, teile); return undefined; }
    offen.delete(teil.stueck);
    return JSON.parse(teile.join(""));
  };
}

// Legt das Zerlegen über einen Kanal: Wer ihn benutzt, merkt davon nichts.
function stueckweise(kanal) {
  let nummer = 0;
  const zusammen = zusammensetzer();
  return {
    senden: (daten) => { for (const teil of zerlegen(daten, nummer++)) kanal.senden(teil); },
    beiNachricht: (fn) => kanal.beiNachricht((teil) => {
      let daten;
      try { daten = zusammen(teil); } catch { return; }  // kaputtes Stück: ignorieren
      if (daten !== undefined) fn(daten);
    }),
    beiEnde: (fn) => kanal.beiEnde(fn),
    schliessen: () => kanal.schliessen(),
  };
}

function kanalAusPeer(verbindung, peer = null) {
  const hoerer = { nachricht: () => {}, ende: () => {} };
  verbindung.on("data", (daten) => hoerer.nachricht(daten));
  verbindung.on("close", () => hoerer.ende());
  verbindung.on("error", () => hoerer.ende());
  return {
    senden: (daten) => { if (verbindung.open) verbindung.send(daten); },
    beiNachricht: (fn) => { hoerer.nachricht = fn; },
    beiEnde: (fn) => { hoerer.ende = fn; },
    schliessen: () => { verbindung.close(); peer?.destroy(); },
  };
}

async function raumOeffnen(raum, beiKanalRoh, beiStatus) {
  const beiKanal = (kanal) => beiKanalRoh(stueckweise(kanal));
  if (lokal()) {
    const funk = new BroadcastChannel(raum);
    const kanaele = new Map();
    funk.onmessage = ({ data }) => {
      if (!data || data.an !== "gastgeber") return;
      let kanal = kanaele.get(data.von);
      if (!kanal) {
        const hoerer = { nachricht: () => {}, ende: () => {} };
        kanal = {
          senden: (daten) => funk.postMessage({ an: data.von, daten }),
          beiNachricht: (fn) => { hoerer.nachricht = fn; },
          beiEnde: (fn) => { hoerer.ende = fn; },
          schliessen: () => kanaele.delete(data.von),
          hoerer,
        };
        kanaele.set(data.von, kanal);
        beiKanal(kanal);
      }
      if (data.ende) { kanaele.delete(data.von); kanal.hoerer.ende(); } else kanal.hoerer.nachricht(data.daten);
    };
    beiStatus("bereit");
    return;
  }
  const Peer = await peerLaden();
  const starten = () => {
    const peer = new Peer(raum);
    peer.on("open", () => beiStatus("bereit"));
    peer.on("connection", (verbindung) => verbindung.on("open", () => beiKanal(kanalAusPeer(verbindung))));
    peer.on("disconnected", () => { beiStatus("getrennt"); if (!peer.destroyed) peer.reconnect(); });
    peer.on("error", (fehler) => {
      // Nach einem Neuladen ist der Raum beim Vermittler noch kurz belegt: gleich noch einmal.
      beiStatus(fehler.type === "unavailable-id" ? "warte" : `fehler: ${fehler.type}`);
      if (["unavailable-id", "network", "server-error", "socket-error", "socket-closed"].includes(fehler.type)) {
        peer.destroy();
        setTimeout(starten, 4000);
      }
    });
  };
  starten();
}

async function raumBetreten(raum, beiStatus) {
  return stueckweise(await raumBetretenRoh(raum, beiStatus));
}

async function raumBetretenRoh(raum, beiStatus) {
  if (lokal()) {
    const funk = new BroadcastChannel(raum);
    const ich = zufall(8);
    const hoerer = { nachricht: () => {}, ende: () => {} };
    funk.onmessage = ({ data }) => { if (data && data.an === ich) hoerer.nachricht(data.daten); };
    addEventListener("pagehide", () => funk.postMessage({ an: "gastgeber", von: ich, ende: true }));
    beiStatus("verbunden");
    return {
      senden: (daten) => funk.postMessage({ an: "gastgeber", von: ich, daten }),
      beiNachricht: (fn) => { hoerer.nachricht = fn; },
      beiEnde: (fn) => { hoerer.ende = fn; },
      schliessen: () => funk.close(),
    };
  }
  const Peer = await peerLaden();
  return new Promise((fertig, fehler) => {
    const peer = new Peer();
    // Scheitert die direkte Verbindung lautlos (strenges Netz), nicht ewig warten.
    const abbruch = setTimeout(() => { peer.destroy(); fehler(new Error("Zeitüberschreitung")); }, 15000);
    peer.on("open", () => {
      const verbindung = peer.connect(raum, { reliable: true, serialization: "json" });
      verbindung.on("open", () => { clearTimeout(abbruch); beiStatus("verbunden"); fertig(kanalAusPeer(verbindung, peer)); });
    });
    peer.on("error", (e) => { clearTimeout(abbruch); peer.destroy(); fehler(new Error(e.type)); });
  });
}

// --- Gastgeber -------------------------------------------------------------------

// Was ein Gast schickt, ist nicht vertrauenswürdig: nur Text-Werte, begrenzt. Sonst könnte ein
// kaputter Zug die gespeicherte Partie unspielbar machen (sie wird bei jedem Laden wiederholt).
export function sauber(parameter) {
  if (!parameter || typeof parameter !== "object" || Array.isArray(parameter)) return {};
  return Object.fromEntries(Object.entries(parameter)
    .filter(([name, wert]) => /^\w{1,30}$/.test(name) && typeof wert === "string")
    .slice(0, 5)
    .map(([name, wert]) => [name, wert.slice(0, 2000)]));
}

// Nur das, was der Gast an Platz `platz` sehen darf. Die Partie läuft beim Gastgeber, die
// Geheimnisse der anderen bleiben dort.
export function fuerGast(z, ereignisse, platz) {
  const nur = (objekt) => (objekt && platz in objekt ? { [platz]: objekt[platz] } : {});
  const dran = z.frage?.wer;
  return {
    laeuft: true, seed: z.seed, menschen: [platz],
    ereignisse, anzahl: ereignisse.length,
    frage: dran === platz ? z.frage : null,
    karten: nur(z.karten), karte_titel: z.karte_titel, geheimwissen: nur(z.geheimwissen), jetzt_karten: nur(z.jetzt_karten),
    ende: z.ende || null, gewonnen: nur(z.gewonnen),
    fehler: z.fehler ? "Beim Gastgeber ist ein Fehler aufgetreten. Warte, bis er es erneut versucht." : null,
    wiederholbar: false,
    status: dran && dran !== platz ? `${dran} ist dran …` : (z.ende ? "" : z.status || ""),
    protokoll: null, downloads: z.ende ? z.downloads || [] : [],
  };
}

// plaetze: { Ben: "geheimes-zeichen", … } – nur wer das Zeichen seines Platzes kennt, spielt dort.
// api: die Schnittstelle des Gastgebers (Server oder Pyodide). nachZug(): neu abfragen.
export function gastgeberStarten({ raum, plaetze, api, nachZug, beiAenderung }) {
  const verbunden = new Map();  // Platz -> Kanal
  const lebt = new Map();  // Platz -> Zeitpunkt des letzten Lebenszeichens
  let ereignisse = [], seed = null, letzter = null, gesendet = new Map(), status = "verbinde";
  const melden = () => beiAenderung({ status, verbunden: new Set(verbunden.keys()) });

  const senden = (platz) => {
    const kanal = verbunden.get(platz);
    if (!kanal || !letzter) return;
    const stand = fuerGast(letzter, ereignisse, platz);
    const json = JSON.stringify(stand);
    if (gesendet.get(platz) === json) return;  // nichts Neues
    gesendet.set(platz, json);
    kanal.senden({ typ: "zustand", zustand: stand });
  };

  raumOeffnen(raum, (kanal) => {
    let platz = null;
    kanal.beiNachricht(async (nachricht) => {
      if (!nachricht || typeof nachricht !== "object") return;
      if (platz && verbunden.get(platz) === kanal) lebt.set(platz, Date.now());
      if (nachricht.typ === "hallo") {
        if (!(nachricht.platz in plaetze) || plaetze[nachricht.platz] !== nachricht.zeichen) {
          kanal.senden({ typ: "fehler", text: "Dieser Link gehört zu keinem Platz dieser Partie." });
          return;
        }
        platz = nachricht.platz;
        const alt = verbunden.get(platz);
        if (alt && alt !== kanal) alt.schliessen();  // Gast hat neu geladen: alte Verbindung ersetzen
        verbunden.set(platz, kanal);
        lebt.set(platz, Date.now());
        gesendet.delete(platz);
        senden(platz);
        melden();
      } else if (!platz) {
        kanal.senden({ typ: "wer" });  // z. B. nach Neuladen des Gastgebers: Gast soll sich neu melden
      } else if (nachricht.typ === "puls") {
        // nur Lebenszeichen
      } else if (nachricht.typ === "aktion") {
        // Nur annehmen, wenn genau dieser Platz mit genau dieser Frage dran ist.
        const frage = letzter?.frage;
        if (!frage || frage.wer !== platz || nachricht.nummer !== frage.nummer) return;
        await api("/api/aktion", { tool: String(nachricht.tool), parameter: sauber(nachricht.parameter), nummer: frage.nummer });
        nachZug();
      }
    });
    kanal.beiEnde(() => {
      if (platz && verbunden.get(platz) === kanal) { verbunden.delete(platz); melden(); }
    });
  }, (neu) => { status = neu; melden(); });

  setInterval(() => {
    for (const [platz, kanal] of verbunden) {
      if (Date.now() - (lebt.get(platz) || 0) > STILLE_MS) {  // Gast weg (Tab zu, Funkloch …)
        verbunden.delete(platz);
        kanal.schliessen();
        melden();
      } else kanal.senden({ typ: "puls" });
    }
  }, PULS_MS);

  return {
    // Mit jedem Stand der Partie aufrufen (auch den Teilständen mit `seit`).
    verteilen(z) {
      if (z.seed !== seed) { seed = z.seed; ereignisse = []; }
      if (z.anzahl - z.ereignisse.length === ereignisse.length) ereignisse = ereignisse.concat(z.ereignisse);
      letzter = z;
      for (const platz of verbunden.keys()) senden(platz);
    },
    plaetzeSetzen(neu) {
      plaetze = neu;
      for (const [platz, kanal] of verbunden) if (!(platz in neu)) { kanal.schliessen(); verbunden.delete(platz); }
      melden();
    },
  };
}

// --- Gast ---------------------------------------------------------------------------

// Liefert ein Backend für die Seite: api(pfad, daten) wie beim Server.
export async function gastStarten({ raum, platz, zeichen }) {
  let stand = null, hinweis = "Verbinde mit dem Gastgeber …", kanal = null, zuletzt = 0;

  const verloren = () => {
    if (!kanal) return;
    const alt = kanal;
    kanal = null;
    try { alt.schliessen(); } catch { /* schon zu */ }
    hinweis = "Verbindung zum Gastgeber verloren – verbinde neu …";
    setTimeout(verbinden, 1000);
  };

  const verbinden = async () => {
    try {
      kanal = await raumBetreten(raum, () => {});
      zuletzt = Date.now();
      hinweis = "Verbunden. Warte auf den Gastgeber …";
      kanal.beiNachricht((nachricht) => {
        zuletzt = Date.now();
        if (nachricht?.typ === "zustand") stand = nachricht.zustand;
        if (nachricht?.typ === "fehler") hinweis = nachricht.text;
        if (nachricht?.typ === "wer") kanal?.senden({ typ: "hallo", platz, zeichen });
      });
      kanal.beiEnde(verloren);
      kanal.senden({ typ: "hallo", platz, zeichen });
    } catch {
      hinweis = "Gastgeber nicht erreichbar – ist seine Seite noch offen? Versuche es weiter …";
      setTimeout(verbinden, 4000);
    }
  };
  verbinden();
  setInterval(() => {
    if (!kanal) return;
    if (Date.now() - zuletzt > STILLE_MS) return verloren();  // Gastgeber schweigt: neu verbinden
    // Solange noch nichts vom Gastgeber kam (er lädt z. B. noch Python), regelmäßig neu melden.
    kanal.senden(stand ? { typ: "puls" } : { typ: "hallo", platz, zeichen });
  }, PULS_MS);

  return {
    async api(pfad, daten) {
      const url = new URL(pfad, location.href);
      const antwort = (status, inhalt) => ({ status, daten: inhalt });
      if (url.pathname.endsWith("/api/zustand")) {
        if (!stand) return antwort(200, { laeuft: false, gast: true, status: hinweis });
        const seit = Number(url.searchParams.get("seit")) || 0;
        const status = kanal ? stand.status : hinweis;
        return antwort(200, { ...stand, ereignisse: stand.ereignisse.slice(seit), status, gast: true });
      }
      if (url.pathname.endsWith("/api/aktion")) {
        if (!kanal) return antwort(409, { fehler: "Keine Verbindung zum Gastgeber" });
        kanal.senden({ typ: "aktion", tool: daten.tool, parameter: daten.parameter, nummer: daten.nummer });
        return antwort(200, { ok: true });
      }
      if (url.pathname.endsWith("/api/optionen")) return antwort(200, { namen: [], szenarien: [] });
      if (url.pathname.endsWith("/api/neu")) return antwort(400, { fehler: "Nur der Gastgeber kann eine Partie starten." });
      return antwort(200, { ok: true });
    },
  };
}
