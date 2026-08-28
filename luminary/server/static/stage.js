/* Stage client: the play-queue page (luminary/stage/web.py).
 *
 * A thin adapter over the stage API (implementation-notes §2.9): the
 * canvas decodes the one wire stream with the standard decoder (via
 * mapping.js's StreamView/WireStream — the exact draw-list approach the
 * mapping page uses), and the queue panel renders GET /api/queue and
 * sends commands — every playback decision lives server-side in
 * StageCore. State refreshes by polling every ~2s plus immediately
 * after each command this page sends. Every URL is page-relative
 * (mapping.js's BASE), so the page serves at any mount prefix.
 */

import { BASE, StreamView, WireStream } from "./mapping.js";

const POLL_MS = 2000;

const el = (id) => document.getElementById(id);

async function getJSON(path) {
  const response = await fetch(new URL(path, BASE));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function send(path, options) {
  const response = await fetch(new URL(path, BASE), options);
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

  const pat = document.createElement("span");
  pat.className = "pat";
  pat.textContent = entry.pattern + (entry.audio ? ` ♪ ${entry.audio}` : "");
  pat.title = pat.textContent;
  row.appendChild(pat);

  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = playing
    ? `${fmtSeconds(now.elapsed)} / ${fmtSeconds(now.length)}`
    : fmtSeconds(entry.duration);
  row.appendChild(meta);

  const act = (label, fn) => {
    const button = document.createElement("button");
    button.textContent = label;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      fn().catch(report);
    });
    row.appendChild(button);
  };
  // Upcoming entries reorder within the upcoming range; playing and
  // upcoming remove (removing the playing entry advances server-side).
  if (i > now.index + 1) act("↑", () => move(i, i - 1));
  if (i > now.index && i < entries.length - 1) act("↓", () => move(i, i + 1));
  if (i >= now.index) act("✕", () => remove(i));
  return row;
}

function renderQueue(snapshot) {
  const box = el("queue");
  box.replaceChildren();
  const { entries, now } = snapshot;
  entries.forEach((entry, i) => box.appendChild(entryRow(entry, i, snapshot)));
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "queue is empty — the stage holds the last pattern";
    box.appendChild(empty);
  }

  const hold = now.holding ? ` <span class="hold">· holding (loop)</span>` : "";
  el("now").innerHTML =
    `<b></b> · ${fmtSeconds(now.elapsed)} / ${fmtSeconds(now.length)}${hold}`;
  el("now").querySelector("b").textContent = now.pattern;
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

/* ----------------------------------------------------------- the page */

export async function initStagePage() {
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

  // Dropdowns: patterns from the server registry, audio files from var/audio.
  const [patterns, audio] = await Promise.all([
    getJSON("api/patterns"),
    getJSON("api/audio"),
  ]);
  const patternSelect = el("add-pattern");
  for (const entry of patterns.filter((p) => p.ok)) {
    const option = document.createElement("option");
    option.value = entry.name;
    option.textContent = entry.name;
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

  el("add-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const duration = el("add-duration").value;
    post("api/queue", {
      pattern: patternSelect.value,
      duration: duration ? Number(duration) : null,
      audio: audioSelect.value || null,
    }).catch(report);
  });
  el("skip").addEventListener("click", () => post("api/queue/skip").catch(report));
  el("clear").addEventListener("click", () => {
    if (confirm("Drop every queue entry? (The stage keeps playing.)")) {
      post("api/queue/clear").catch(report);
    }
  });

  refresh = () => getJSON("api/queue").then(renderQueue).catch(report);
  await refresh();
  setInterval(refresh, POLL_MS);
}
