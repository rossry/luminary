/* Vibe client: prompt-to-pattern on the stage (luminary/vibe/web.py).
 *
 * A thin adapter: the canvas decodes the stage's own wire stream (the
 * same StreamView/WireStream the stage page uses — vibe mode has no
 * second render), and everything else on the page is GET /api/vibe
 * rendered every ~2 s plus immediately after each verb this page sends.
 * All state is the server's: the thread of generations, what is cooking,
 * what is showing, the menu. Open this page in five places and they
 * agree. Mutations carry the stage key (shared with the stage page via
 * the same localStorage slot).
 */

import { BASE, StreamView, WireStream } from "./mapping.js";

const POLL_MS = 2000;
const KEY_STORE = "luminary-stage-key";
const MODEL_STORE = "luminary-vibe-model";
const AUTHOR_STORE = "luminary-vibe-author";

const el = (id) => document.getElementById(id);

let stageKey = "";

function initKey() {
  const fromHash = new URLSearchParams(location.hash.slice(1)).get("key");
  if (fromHash) {
    try { localStorage.setItem(KEY_STORE, fromHash); } catch {}
    history.replaceState(null, "", location.pathname + location.search);
  }
  try { stageKey = localStorage.getItem(KEY_STORE) || ""; } catch { stageKey = ""; }
  const field = el("stage-key");
  field.value = stageKey;
  field.addEventListener("change", () => {
    stageKey = field.value.trim();
    try { localStorage.setItem(KEY_STORE, stageKey); } catch {}
  });
}

async function getJSON(path) {
  const response = await fetch(new URL(path, BASE));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function post(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (stageKey) headers["X-Stage-Key"] = stageKey;
  const response = await fetch(new URL(path, BASE), {
    method: "POST", headers, body: JSON.stringify(body || {}),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

const report = (error) => { el("status").textContent = String(error.message || error); };

/* ------------------------------------------------------------ rendering */

function item(text, sub, opts) {
  const row = document.createElement("div");
  row.className = "item" + (opts.playing ? " playing" : "");
  if (opts.n !== undefined) {
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = `#${opts.n}`;
    row.appendChild(n);
  }
  const t = document.createElement("span");
  t.className = "text";
  t.textContent = text;
  t.title = opts.title || text;
  row.appendChild(t);
  if (sub) {
    const w = document.createElement("span");
    w.className = "who";
    w.textContent = sub;
    row.appendChild(w);
  }
  row.addEventListener("click", () => select(opts.pattern));
  return row;
}

function renderMenu(snap) {
  const box = el("menu");
  box.replaceChildren();
  const playing = snap.now.pattern;
  const section = (label) => {
    const s = document.createElement("div");
    s.className = "section";
    s.textContent = label;
    box.appendChild(s);
  };
  if (snap.menu.named.length) {
    section("named");
    for (const g of snap.menu.named) {
      box.appendChild(item(g.name, g.author, {
        n: g.n, pattern: g.pattern, playing: g.pattern === playing, title: g.prompt,
      }));
    }
  }
  section("all");
  if (!snap.menu.all.length) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = "nothing yet";
    box.appendChild(e);
  }
  for (const g of snap.menu.all) {
    box.appendChild(item(g.name || g.prompt, g.author, {
      n: g.n, pattern: g.pattern, playing: g.pattern === playing, title: g.prompt,
    }));
  }
  for (const group of snap.menu.repo) {
    section(group.folder);
    for (const p of group.patterns) {
      box.appendChild(item(p.name, "", {
        pattern: p.name, playing: p.name === playing, title: p.description,
      }));
    }
  }
}

function genRow(g, playing) {
  const row = document.createElement("div");
  row.className = "gen " + g.status + (g.pattern === playing ? " playing" : "");
  const head = document.createElement("div");
  head.className = "head";
  const n = document.createElement("span");
  n.className = "n";
  n.textContent = `#${g.n}`;
  head.appendChild(n);
  if (g.name) {
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = g.name;
    head.appendChild(name);
  }
  const who = document.createElement("span");
  who.className = "who";
  const done = g.status === "ok" || g.status === "failed";
  who.textContent =
    (g.author || "") +
    (g.status === "queued" ? " · queued" : g.status === "cooking" ? " · cooking…" : "") +
    (g.model ? ` · ${g.model.replace(/^claude-/, "")}` : "") +
    (done && g.seconds != null ? ` · ${Math.round(g.seconds)} s` : "");
  head.appendChild(who);
  row.appendChild(head);
  const prompt = document.createElement("div");
  prompt.className = "prompt";
  prompt.textContent = g.prompt;
  row.appendChild(prompt);
  if (g.shown && !g.from_scratch) {
    const ctx = document.createElement("div");
    ctx.className = "ctx";
    ctx.textContent = `while ${g.shown_title || g.shown} was showing`;
    row.appendChild(ctx);
  }
  if (g.note) {
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = g.note;
    row.appendChild(note);
  }
  if (g.status === "failed") {
    const err = document.createElement("div");
    err.className = "err";
    err.textContent = (g.error || "failed").split("\n").slice(-2).join("\n");
    row.appendChild(err);
  }
  if (g.status === "ok") row.addEventListener("click", () => select(g.pattern));
  return row;
}

function renderThread(snap) {
  const box = el("thread");
  box.replaceChildren();
  if (!snap.generations.length) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = snap.enabled ? "say something" : "no coding model — set ANTHROPIC_API_KEY on the server";
    box.appendChild(e);
  }
  for (const g of snap.generations) box.appendChild(genRow(g, snap.now.pattern));
}

function render(snap) {
  renderMenu(snap);
  renderThread(snap);
  const now = snap.now;
  el("now").innerHTML = `<b></b>` + (now.author ? ` · ${now.author}` : "");
  el("now").querySelector("b").textContent = now.title || now.pattern;
  el("liner").textContent = now.notes || now.prompt || "";
  el("liner").title = el("liner").textContent;
  const working = snap.working;
  el("backend").textContent =
    (snap.enabled ? snap.backend : "no model") +
    (working ? ` · cooking #${working.n}` : snap.queue.length ? ` · ${snap.queue.length} queued` : "");
  const modelSelect = el("model");
  if (modelSelect.options.length !== snap.models.length) {
    const keep = modelSelect.value;
    modelSelect.replaceChildren();
    for (const m of snap.models) {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m.replace(/^claude-/, "");
      modelSelect.appendChild(o);
    }
    let want = keep;
    try { want = want || localStorage.getItem(MODEL_STORE) || ""; } catch {}
    if (want && snap.models.includes(want)) modelSelect.value = want;
  }
}

/* -------------------------------------------------------------- verbs */

let refresh = () => {};

const select = (pattern) =>
  post("api/vibe/select", { pattern }).then(render).catch(report);

/* ------------------------------------------------------------- the page */

export async function initVibePage() {
  initKey();
  const layout = await getJSON("api/stage/layout");
  const view = new StreamView(el("stage-canvas"));
  view.setLayout(layout);
  const stream = new WireStream(
    "api/stage",
    (bytes) => { if (view.feed(bytes)) stream.send({ type: "resync" }); },
    (status) => { el("status").textContent = status; }
  );
  const paintLoop = () => {
    if (view.needsPaint && !document.hidden) view.paint();
    requestAnimationFrame(paintLoop);
  };
  requestAnimationFrame(paintLoop);

  el("menu-toggle").addEventListener("click", () => el("menu").classList.toggle("hidden"));
  try { el("author").value = localStorage.getItem(AUTHOR_STORE) || ""; } catch {}
  el("author").addEventListener("change", () => {
    try { localStorage.setItem(AUTHOR_STORE, el("author").value.trim()); } catch {}
  });
  el("model").addEventListener("change", () => {
    try { localStorage.setItem(MODEL_STORE, el("model").value); } catch {}
  });

  el("vibe-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const prompt = el("prompt").value.trim();
    if (!prompt) return;
    const body = {
      prompt,
      name: el("name").value.trim(),
      author: el("author").value.trim(),
      model: el("model").value,
      from_scratch: el("scratch").checked,
    };
    el("prompt").value = "";
    el("name").value = "";
    post("api/vibe", body).then(() => refresh()).catch(report);
  });

  refresh = () => getJSON("api/vibe").then(render).catch(report);
  await refresh();
  setInterval(refresh, POLL_MS);
}
