/* Stage client: the play-queue page (luminary/stage/web.py).
 *
 * A thin adapter over the stage API (implementation-notes §2.9): the
 * canvas decodes the one wire stream with the standard decoder (via
 * mapping.js's StreamView/WireStream — the exact draw-list approach the
 * mapping page uses), and the queue panel renders GET /api/queue and
 * sends commands — every playback decision (chapter expansion, seamless
 * advance, the repeats cycle) lives server-side in StageCore. Chapter
 * trees and pattern metadata (loop flags, has_chapters) are fetched from
 * the server, never computed here; the queued-row chapter preview is
 * display only. State refreshes by polling every ~2s plus immediately
 * after each command this page sends. Every URL is page-relative
 * (mapping.js's BASE), so the page serves at any mount prefix.
 *
 * Access: mutating requests carry the stage key (when the operator has
 * one) in an X-Stage-Key header — entered in the footer field
 * (persisted in localStorage) or handed over once as a #key=… URL
 * fragment. A 403's JSON detail surfaces on the status line.
 */

import { BASE, StreamView, WireStream } from "./mapping.js";

const POLL_MS = 2000;
const KEY_STORE = "luminary-stage-key";

const el = (id) => document.getElementById(id);

/* ---------------------------------------------------------- stage key */

let stageKey = "";

function initKey() {
  const fromHash = new URLSearchParams(location.hash.slice(1)).get("key");
  if (fromHash) {
    try { localStorage.setItem(KEY_STORE, fromHash); } catch {}
    // Don't leave the key sitting in a shareable URL.
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

/* ------------------------------------------------------------ fetches */

async function getJSON(path) {
  const response = await fetch(new URL(path, BASE));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function send(path, options) {
  const headers = Object.assign({}, options && options.headers);
  if (stageKey) headers["X-Stage-Key"] = stageKey;
  const response = await fetch(new URL(path, BASE), { ...options, headers });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

const fmtSeconds = (s) => {
  if (s === null || s === undefined) return "∞";
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
};

/* ------------------------------------------------------- queue rendering */

const patternMeta = new Map(); // name -> {loop, has_chapters, notes, ...}
const chapterCache = new Map(); // name -> chapters tree (display only)
const openPreviews = new Set(); // row keys with the chapter preview open

const rowKey = (entry, i) => `${i}|${entry.pattern}|${entry.offset}`;

function actButton(parent, label, fn) {
  const button = document.createElement("button");
  button.textContent = label;
  button.addEventListener("click", (event) => {
    event.preventDefault();
    fn().catch(report);
  });
  parent.appendChild(button);
}

function entryRow(entry, i, snapshot) {
  const { entries, now } = snapshot;
  const row = document.createElement("div");
  row.className = "entry";
  const playing = !now.holding && i === now.index;
  if (playing) row.classList.add("playing");
  else if (i < now.index) row.classList.add("played");

  const marker = document.createElement("span");
  marker.textContent = playing ? "▶" : i < now.index ? "✓" : `${i - now.index}·`;
  row.appendChild(marker);

  const meta = patternMeta.get(entry.pattern);
  const expandable = entry.chapter === null && meta && meta.has_chapters;

  const pat = document.createElement("span");
  pat.className = "pat";
  const title = entry.title || entry.pattern;
  pat.textContent =
    (expandable ? (openPreviews.has(rowKey(entry, i)) ? "▾ " : "▸ ") : "") +
    (entry.repeat ? "↻ " : "") +
    title +
    (entry.audio ? ` ♪ ${entry.audio}` : "");
  pat.title = entry.notes || title;
  row.appendChild(pat);

  const time = document.createElement("span");
  time.className = "meta";
  time.textContent = playing
    ? `${fmtSeconds(now.elapsed)} / ${fmtSeconds(now.length)}`
    : fmtSeconds(entry.duration);
  row.appendChild(time);

  if (expandable) {
    // A queued composition is a click-to-preview expander: its chapter
    // list comes from the server (it expands for real at the head).
    row.classList.add("expandable");
    pat.addEventListener("click", () => togglePreview(rowKey(entry, i)));
  }

  // [↑][↓] immediately left of [✕]: upcoming entries reorder within the
  // upcoming range; playing and upcoming remove (removing the playing
  // entry advances server-side).
  if (i > now.index + 1) actButton(row, "↑", () => move(i, i - 1));
  if (i > now.index && i < entries.length - 1) actButton(row, "↓", () => move(i, i + 1));
  if (i >= now.index) actButton(row, "✕", () => remove(i));
  return row;
}

function appendChapterLines(box, nodes, depth) {
  for (const node of nodes) {
    const line = document.createElement("div");
    line.className = "chapter";
    line.style.paddingLeft = `${1.4 + depth * 0.9}rem`;
    line.textContent = `${node.title} `;
    const dur = document.createElement("span");
    dur.className = "dur";
    dur.textContent = `· ${fmtSeconds(node.duration)}`;
    line.appendChild(dur);
    if (node.notes) line.title = node.notes;
    box.appendChild(line);
    if (node.children) appendChapterLines(box, node.children, depth + 1);
  }
}

function chapterPreview(name) {
  const box = document.createElement("div");
  box.className = "chapters";
  const tree = chapterCache.get(name);
  if (!tree) {
    box.textContent = "…";
    getJSON(`api/stage/chapters?pattern=${encodeURIComponent(name)}`)
      .then((fetched) => { chapterCache.set(name, fetched); refresh(); })
      .catch(report);
  } else {
    appendChapterLines(box, tree, 0);
  }
  return box;
}

function togglePreview(key) {
  if (openPreviews.has(key)) openPreviews.delete(key);
  else openPreviews.add(key);
  refresh();
}

function repeatRow(token, i, count) {
  const row = document.createElement("div");
  row.className = "repeat-row";
  const pat = document.createElement("span");
  pat.className = "pat";
  pat.textContent = `↻ ${token.title || token.pattern}` +
    (token.audio ? ` ♪ ${token.audio}` : "");
  pat.title = pat.textContent;
  row.appendChild(pat);
  if (i > 0) actButton(row, "↑", () => moveRepeat(i, i - 1));
  if (i < count - 1) actButton(row, "↓", () => moveRepeat(i, i + 1));
  actButton(row, "✕", () => removeRepeat(i));
  return row;
}

function renderQueue(snapshot) {
  const box = el("queue");
  box.replaceChildren();
  const { entries, repeats, now } = snapshot;
  entries.forEach((entry, i) => {
    box.appendChild(entryRow(entry, i, snapshot));
    if (entry.chapter === null && openPreviews.has(rowKey(entry, i))) {
      box.appendChild(chapterPreview(entry.pattern));
    }
  });
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "queue is empty — the stage holds the last pattern";
    box.appendChild(empty);
  }

  const rbox = el("repeats");
  rbox.replaceChildren();
  (repeats || []).forEach((token, i) =>
    rbox.appendChild(repeatRow(token, i, repeats.length)));
  if (!repeats || !repeats.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "no repeats — add with ☑ repeat to keep a cycle going";
    rbox.appendChild(empty);
  }

  const hold = now.holding ? ` <span class="hold">· holding (loop)</span>` : "";
  el("now").innerHTML =
    `<b></b> · ${fmtSeconds(now.elapsed)} / ${fmtSeconds(now.length)}${hold}`;
  el("now").querySelector("b").textContent = now.title || now.pattern;
  const liner = el("liner");
  liner.textContent = now.notes || "";
  liner.title = now.notes || "";
  el("audio-note").textContent = snapshot.audio_player
    ? `audio: ${snapshot.audio_player}${snapshot.audio_playing ? " · playing" : ""}`
    : "audio disabled (no player on server)";
}

/* ----------------------------------------------------------- commands */

let refresh = () => {};
const report = (error) => { el("status").textContent = String(error.message || error); };

const post = (path, body) =>
  send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then((snap) => renderQueue(snap));

const move = (from, to) => post("api/queue/move", { from, to });
const remove = (i) =>
  send(`api/queue/${i}`, { method: "DELETE" }).then((snap) => renderQueue(snap));
const moveRepeat = (from, to) => post("api/repeats/move", { from, to });
const removeRepeat = (i) =>
  send(`api/repeats/${i}`, { method: "DELETE" }).then((snap) => renderQueue(snap));

/* ----------------------------------------------------------- the page */

export async function initStagePage() {
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

  // Dropdowns: pattern metadata from the stage (adds notes/loop/chapter
  // flags to the registry list), audio files from var/audio.
  const [patterns, audio] = await Promise.all([
    getJSON("api/stage/patterns"),
    getJSON("api/audio"),
  ]);
  const patternSelect = el("add-pattern");
  for (const entry of patterns.filter((p) => p.ok)) {
    patternMeta.set(entry.name, entry);
    const option = document.createElement("option");
    option.value = entry.name;
    option.textContent =
      entry.name + (entry.has_chapters ? " ▸" : "") + (entry.loop ? " ↻" : "");
    option.title = entry.description || "";
    patternSelect.appendChild(option);
  }
  const audioSelect = el("add-audio");
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "— no audio —";
  audioSelect.appendChild(none);
  for (const name of audio) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = `♪ ${name}`;
    audioSelect.appendChild(option);
  }

  // Per-pattern defaults: the repeat toggle follows the pattern's own
  // loop flag, and the audio selector pre-selects the pattern's
  // declared soundtrack when the file is present in var/audio. The VJ
  // can always override either per add.
  const repeatBox = el("add-repeat");
  const syncPatternDefaults = () => {
    const meta = patternMeta.get(patternSelect.value);
    repeatBox.checked = !!(meta && meta.loop);
    audioSelect.value = meta && meta.audio_present ? meta.audio : "";
    if (meta && meta.audio && !meta.audio_present) {
      none.textContent = `— no audio (wants ♪ ${meta.audio}) —`;
    } else {
      none.textContent = "— no audio —";
    }
  };
  patternSelect.addEventListener("change", syncPatternDefaults);
  syncPatternDefaults();

  const addBody = () => {
    const duration = el("add-duration").value;
    return {
      pattern: patternSelect.value,
      duration: duration ? Number(duration) : null,
      // The page always states its choice: "" is explicitly no audio
      // (the server-side declared-audio default applies only when the
      // field is omitted entirely).
      audio: audioSelect.value,
      repeat: repeatBox.checked,
    };
  };
  el("add-form").addEventListener("submit", (event) => {
    event.preventDefault();
    post("api/queue", addBody()).catch(report);
  });
  el("play-next").addEventListener("click", () => {
    post("api/queue/play_next", addBody()).catch(report);
  });
  el("skip").addEventListener("click", () => post("api/queue/skip").catch(report));
  el("clear").addEventListener("click", () => {
    if (confirm("Drop every play-through entry? (The stage keeps playing; repeats keep cycling.)")) {
      post("api/queue/clear").catch(report);
    }
  });

  refresh = () => getJSON("api/queue").then(renderQueue).catch(report);
  await refresh();
  setInterval(refresh, POLL_MS);
}
