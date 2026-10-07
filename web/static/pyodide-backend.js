// Server-Ersatz für GitHub Pages: Python läuft per Pyodide direkt im Browser.
//
// Die Seite (index.html) spricht dieselben /api-Adressen an wie beim Python-Server.
// Hier werden sie beantwortet, indem web/browser.py die Partie von vorn spielt,
// bis eine Antwort fehlt (siehe dort). Fehlt eine LLM-Antwort, holt dieses Skript
// sie mit deinem API-Key beim Anbieter. Der Key verlässt deinen Browser nur dorthin.

let py = null;            // web/browser.py als Python-Modul
let hilfen = null;        // { zugang() } aus index.html: liest Adresse, Modell, Key
let partie = null;        // laufende Partie, siehe neuePartie()
let lauf = 0;             // Nummer des aktuellen Spiel-Laufs; ein neuer beendet den alten
let letzteAnfrage = 0;    // Zeitpunkt des letzten LLM-Aufrufs (für das Tempolimit)

const SPEICHER = "werwolf-partie";

export async function starten(h) {
  hilfen = h;
  const { loadPyodide } = await import("./pyodide/pyodide.mjs");
  const pyodide = await loadPyodide({ indexURL: new URL("./pyodide/", import.meta.url).href });
  const zip = await fetch(new URL("./werwolf-ki.zip", import.meta.url)).then((r) => r.arrayBuffer());
  pyodide.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/werwolf" });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide/werwolf')");
  py = pyodide.pyimport("web.browser");

  // Eine Partie vom letzten Besuch? Dank Wiederholen geht es genau dort weiter.
  try {
    const gespeichert = JSON.parse(localStorage.getItem(SPEICHER) || "null");
    if (gespeichert) { partie = { ...gespeichert, zustand: null, fehler: null, status: "" }; weiter(); }
  } catch { /* nichts gespeichert */ }
}

// --- Die /api-Adressen ------------------------------------------------------

export async function api(pfad, daten) {
  const url = new URL(pfad, location.href);
  const antwort = (status, inhalt) => ({ status, daten: inhalt });

  if (url.pathname.endsWith("/api/optionen")) {
    return antwort(200, JSON.parse(py.optionen_json(Number(url.searchParams.get("spieler")) || 0)));
  }
  if (url.pathname.endsWith("/api/zustand")) {
    if (!partie) return antwort(200, { laeuft: false });
    return antwort(200, zustand(Number(url.searchParams.get("seit")) || 0));
  }
  if (url.pathname.endsWith("/api/neu")) {
    const pruefung = JSON.parse(py.einstellungen_json(JSON.stringify(daten)));
    if (pruefung.fehler) return antwort(400, pruefung);
    if (daten.llm !== "0" && !hilfen.zugang().key) {
      return antwort(400, { fehler: "Für LLM-Mitspieler trage unten deinen API-Key ein – oder wähle „keine“." });
    }
    partie = {
      einstellungen: daten, seed: Math.floor(Math.random() * 1_000_000),
      mensch: [], llm: [], zustand: null, fehler: null, status: "",
    };
    weiter();
    return antwort(200, { ok: true });
  }
  if (url.pathname.endsWith("/api/aktion")) {
    const frage = partie?.zustand?.frage;
    // Nur eine Antwort pro Frage: Ein Doppelklick darf nicht den nächsten Zug beantworten.
    if (!frage || daten.nummer !== frage.nummer) return antwort(409, { fehler: "Gerade ist niemand von dir gefragt" });
    partie.mensch.push({ tool: daten.tool, parameter: daten.parameter || {} });
    partie.zustand = { ...partie.zustand, frage: null };
    weiter();
    return antwort(200, { ok: true });
  }
  if (url.pathname.endsWith("/api/weiter")) {  // nach einem Fehler erneut versuchen
    if (partie) { partie.fehler = null; weiter(); }
    return antwort(200, { ok: true });
  }
  return antwort(404, { fehler: "Nicht gefunden" });
}

function zustand(seit) {
  const z = partie.zustand || { ereignisse: [], geheimwissen: [] };
  const downloads = z.ende ? [
    { name: `werwolf_${partie.seed}.txt`, text: z.protokoll },
    { name: `werwolf_${partie.seed}.jsonl`, text: z.log },
  ] : [];
  return {
    laeuft: true, ich: partie.einstellungen.ich, seed: partie.seed,
    ereignisse: z.ereignisse.slice(seit), anzahl: z.ereignisse.length,
    frage: z.frage || null, geheimwissen: z.geheimwissen, karte: z.karte || null, karte_titel: z.karte_titel || null,
    ende: z.ende || null, gewonnen: z.gewonnen ?? null,
    fehler: partie.fehler, wiederholbar: Boolean(partie.fehler), status: partie.status, downloads,
  };
}

// --- Spielen: wiederholen, bis eine Antwort fehlt -----------------------------

async function weiter() {
  const meinLauf = ++lauf;
  const p = partie;
  try {
    while (meinLauf === lauf) {
      speichern(p);
      const z = JSON.parse(py.schritt_json(JSON.stringify({
        einstellungen: p.einstellungen, seed: p.seed, antworten_mensch: p.mensch,
        antworten_llm: p.llm, modell: p.einstellungen.llm === "0" ? "" : hilfen.zugang().modell,
      })));
      if (z.fehler) { p.fehler = z.fehler; return; }
      p.zustand = z;
      if (!z.llm_anfrage) {  // deine Frage oder das Ende: warten auf dich
        p.status = "";
        if (z.ende) localStorage.removeItem(SPEICHER);
        return;
      }
      p.status = `Ein LLM-Mitspieler überlegt … (Aufruf ${p.llm.length + 1})`;
      const roh = await llmFragen(z.llm_anfrage, p);
      if (meinLauf !== lauf) return;  // inzwischen neue Partie gestartet
      p.llm.push(roh);
    }
  } catch (fehler) {
    if (meinLauf === lauf) { p.fehler = String(fehler.message || fehler); p.status = ""; }
  }
}

function speichern(p) {
  try {
    localStorage.setItem(SPEICHER, JSON.stringify({ einstellungen: p.einstellungen, seed: p.seed, mensch: p.mensch, llm: p.llm }));
  } catch { /* zu groß oder privater Modus: dann ohne Fortsetzen nach Neuladen */ }
}

const warten = (ms) => new Promise((fertig) => setTimeout(fertig, ms));

async function llmFragen(anfrage, p) {
  const zugang = hilfen.zugang();
  if (!zugang.key) throw new Error("Kein API-Key eingetragen (unten bei „LLM-Zugang“).");
  const url = zugang.basis.replace(/\/?$/, "/") + "chat/completions";

  for (let versuch = 0; ; versuch++) {
    // Tempolimit: höchstens so viele Anfragen pro Minute (kostenlose Tarife sind knapp).
    const abstand = Number(zugang.tempo) > 0 ? 60000 / Number(zugang.tempo) : 0;
    const rest = letzteAnfrage + abstand - Date.now();
    if (rest > 0) { p.status = `Warte ${Math.ceil(rest / 1000)} s (Tempolimit) …`; await warten(rest); }
    letzteAnfrage = Date.now();

    const antwort = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${zugang.key}` },
      // Die Temperatur kommt aus Python (0,9). Manche Anbieter (GPT-5) nehmen nur 1 an,
      // deshalb darf die Anbieter-Vorlage sie überschreiben.
      body: JSON.stringify({
        ...anfrage, model: zugang.modell,
        ...(zugang.temperatur !== undefined && { temperature: zugang.temperatur }),
      }),
    });
    if (antwort.ok) return antwort.json();

    const text = await antwort.text();
    // 429: zu viele Anfragen. Kurz warten hilft – beim Tageslimit aber nicht.
    if (antwort.status === 429 && !text.includes("PerDay") && versuch < 3) {
      const sekunden = Math.min(60, 10 * 2 ** versuch);
      p.status = `Zu viele Anfragen – warte ${sekunden} s und versuche es erneut …`;
      await warten(sekunden * 1000);
      continue;
    }
    throw new Error(`Der LLM-Anbieter meldet ${antwort.status}: ${text.slice(0, 300)}`);
  }
}
