/* Mapping mirror client (plan/mapping/DESCRIPTION.md, mirror mode).
 *
 * Layout + plan over REST, wire bytes over WS — the streams carry only
 * codec frames, decoded with the standard decoder (spec §14.3); JSON moves
 * control events and state snapshots. mapping.html drives initWindowPage();
 * mapping-demo.js imports the classes and adds the scrambled-build mockup.
 */

import { LumiDecoder, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";

export function pointInTriangle(x, y, tri) {
  const [[ax, ay], [bx, by], [cx, cy]] = tri;
  const s1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
  const s2 = (cx - bx) * (y - by) - (cy - by) * (x - bx);
  const s3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx);
  return (s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0);
}

/* Fit a layout viewBox into a canvas; world -> device transforms. */
export function fitTransform(canvas, viewBox) {
  const [vx, vy, vw, vh] = viewBox;
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  const scale = Math.min(canvas.width / vw, canvas.height / vh);
  const ox = (canvas.width - vw * scale) / 2 - vx * scale;
  const oy = (canvas.height - vh * scale) / 2 - vy * scale;
  return { scale, tx: (x) => x * scale + ox, ty: (y) => y * scale + oy };
}

/* Per-light draw list from a layout (client.js's draw-from-layout shape,
 * flat cells only), plus each light's structural triangle index and the
 * frame overlay segments in device coords. */
export function buildDraws(layout, t) {
  const draws = layout.lights.map((light) => {
    if (light.display && light.display.length >= 3) {
      return {
        kind: "poly",
        points: light.display.map(([px, py]) => [t.tx(px), t.ty(py)]),
        controller: light.controller, channel: light.channel, index: light.index,
      };
    }
    return {
      kind: "dot",
      x: t.tx(light.x), y: t.ty(light.y), r: Math.max(2, 3 * devicePixelRatio),
      controller: light.controller, channel: light.channel, index: light.index,
    };
  });
  const triangles = ((layout.overlays && layout.overlays.triangles) || []).map(
    (tri) => tri.map(([px, py]) => [t.tx(px), t.ty(py)])
  );
  const lightTri = draws.map((d) => {
    let cx, cy;
    if (d.kind === "poly") {
      cx = cy = 0;
      for (const [px, py] of d.points) { cx += px; cy += py; }
      cx /= d.points.length;
      cy /= d.points.length;
    } else {
      cx = d.x; cy = d.y;
    }
    return triangles.findIndex((tri) => pointInTriangle(cx, cy, tri));
  });
  const frame = ((layout.overlays && layout.overlays.frame) || []).map(
    ([a, b]) => [t.tx(a[0]), t.ty(a[1]), t.tx(b[0]), t.ty(b[1])]
  );
  return { draws, lightTri, frame, triangles };
}

export function fillDraw(ctx, d, fill) {
  ctx.fillStyle = fill;
  if (d.kind === "poly") {
    ctx.beginPath();
    ctx.moveTo(d.points[0][0], d.points[0][1]);
    for (let k = 1; k < d.points.length; k++) ctx.lineTo(d.points[k][0], d.points[k][1]);
    ctx.closePath();
    ctx.fill();
  } else {
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.r, 0, 2 * Math.PI);
    ctx.fill();
  }
}

/* One decoded stream painted as flat cells: each layout polygon filled with
 * its light's decoded color, repainting only lights whose color changed. */
export class StreamView {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.decoder = new LumiDecoder();
    this.draws = null;
    this.needsPaint = false;
  }

  setLayout(layout) {
    this.t = fitTransform(this.canvas, layout.viewBox);
    const built = buildDraws(layout, this.t);
    this.draws = built.draws;
    this.frameSegs = built.frame;
    this.lastColor = new Float64Array(this.draws.length * 3).fill(NaN);
    this.resetScene();
  }

  resetScene() {
    const ctx = this.ctx;
    ctx.fillStyle = "#101014";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.strokeStyle = "#26262e";
    ctx.lineWidth = 1.5 * devicePixelRatio;
    ctx.beginPath();
    for (const [x1, y1, x2, y2] of this.frameSegs || []) {
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
    }
    ctx.stroke();
    if (this.lastColor) this.lastColor.fill(NaN);
    this.needsPaint = true;
  }

  /* Feed stream bytes; returns true when the decoder wants a resync.
   * A SESSION frame means the session rebuilt (strips may have changed
   * shape entirely), so the scene repaints from scratch. */
  feed(bytes) {
    const applied = this.decoder.feed(bytes);
    if (applied.some((f) => f.type === FRAME_SESSION)) this.resetScene();
    if (applied.length) this.needsPaint = true;
    const resync = this.decoder.wantResync;
    this.decoder.wantResync = false;
    return resync;
  }

  paint() {
    if (!this.draws) return;
    this.needsPaint = false;
    const ctx = this.ctx;
    const strips = new Map();
    for (let i = 0; i < this.draws.length; i++) {
      const d = this.draws[i];
      const key = `${d.controller}:${d.channel}`;
      if (!strips.has(key)) {
        try {
          strips.set(key, this.decoder.stripOKLCH(d.controller, d.channel));
        } catch {
          strips.set(key, null);
        }
      }
      const strip = strips.get(key);
      let L = -1, C = -1, H = -1; // sentinel: no data yet → paint "#1c1c22" once
      if (strip && d.index * 3 + 2 < strip.length) {
        L = strip[d.index * 3];
        C = strip[d.index * 3 + 1];
        H = strip[d.index * 3 + 2];
      }
      const j = i * 3;
      const last = this.lastColor;
      if (last[j] === L && last[j + 1] === C && last[j + 2] === H) continue;
      last[j] = L;
      last[j + 1] = C;
      last[j + 2] = H;
      let fill = "#1c1c22";
      if (L >= 0) {
        const [r, g, b] = oklchToSrgb8(L, C, H);
        fill = `rgb(${r},${g},${b})`;
      }
      fillDraw(ctx, d, fill);
    }
  }
}

/* Binary WS to a stream endpoint; hands raw bytes to the consumer and
 * carries {"type":"resync"} requests back. */
export class WireStream {
  constructor(path, onBytes, onStatus) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}${path}`);
    this.ws.binaryType = "arraybuffer";
    this.bytes = 0;
    this.ws.onmessage = (event) => {
      const data = new Uint8Array(event.data);
      this.bytes += data.length;
      onBytes(data);
    };
    if (onStatus) {
      this.ws.onopen = () => onStatus("connected");
      this.ws.onclose = () => onStatus("disconnected");
    }
  }

  send(obj) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }
}

/* The control socket: key/button events out, state snapshots in. */
export class ControlChannel {
  constructor(onState, onStatus) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}/api/mapping/control`);
    this.ws.onmessage = (event) => {
      let body;
      try { body = JSON.parse(event.data); } catch { return; }
      if (body.state) onState(body.state);
    };
    if (onStatus) {
      this.ws.onopen = () => onStatus("connected");
      this.ws.onclose = () => onStatus("disconnected");
    }
  }

  send(name) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event: name }));
    }
  }

  /* Arrows and WASD are equivalent; enter confirms (DESCRIPTION.md). */
  bindKeys(target = window) {
    const KEYS = {
      arrowleft: "left", a: "left",
      arrowright: "right", d: "right",
      arrowup: "up", w: "up",
      arrowdown: "down", s: "down",
      enter: "enter",
    };
    target.addEventListener("keydown", (e) => {
      const name = KEYS[e.key.toLowerCase()];
      if (!name || e.altKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      this.send(name);
    });
  }

  bindButtons(root = document) {
    for (const button of root.querySelectorAll("[data-event]")) {
      button.addEventListener("click", () => this.send(button.dataset.event));
    }
  }
}

/* The HUD strip: one line naming the stage, the thing under the cursor,
 * and the live candidates; a progress counter alongside. */
export class Hud {
  constructor(el, progressEl) {
    this.el = el;
    this.progressEl = progressEl || null;
  }

  render(s) {
    const p = s.progress;
    const parts = [];
    if (s.stage === "ports") {
      parts.push(`<span class="chip">stage A · ports→boards</span>`);
      parts.push(`board ${s.board_cursor + 1}/${p.boards_total} — unit ${s.unit_vertex}`);
      parts.push(
        s.candidate_controller === null
          ? `no controller free`
          : `breathing controller <b>${s.candidate_controller}</b>`
      );
      parts.push(`<span class="dim">◀ ▶ cycle boards · ⏎ lock</span>`);
    } else if (s.stage === "panels") {
      const board = s.boards[String(s.unit_vertex)] || {};
      parts.push(`<span class="chip">stage B · panels</span>`);
      parts.push(
        `board ${s.board_cursor + 1}/${p.boards_total} (controller ${board.controller_id})` +
        ` — panel face ${s.face.join("·")}`
      );
      parts.push(
        `channel <b>${s.candidate_channel}</b> · ` +
        `<b>${s.candidate_density}</b> LEDs · <b>${s.candidate_winding}</b>`
      );
      parts.push(`<span class="dim">◀ ▶ channel · ▲ density · ▼ winding · ⏎ confirm</span>`);
    } else {
      parts.push(`<span class="chip done">stage C · mapped</span>`);
      parts.push(`every panel recorded — the sphere is playing the mapped ring`);
    }
    this.el.innerHTML = parts.join(`<span class="sep">·</span>`);
    if (this.progressEl) {
      this.progressEl.textContent =
        `${p.boards_locked}/${p.boards_total} boards · ` +
        `${p.panels_mapped}/${p.panels_total} panels`;
    }
  }
}

const el = (id) => document.getElementById(id);

/* The base-station window page (mapping.html). */
export async function initWindowPage() {
  const meta = await fetch("/api/mapping/layout").then((r) => r.json());
  const view = new StreamView(el("window-canvas"));
  view.setLayout(meta.layout);

  const hud = new Hud(el("hud"), el("progress"));
  hud.render(meta.state);

  const control = new ControlChannel(
    (s) => hud.render(s),
    (status) => (el("status").textContent = status)
  );
  control.bindKeys(window);
  control.bindButtons(document);

  const stream = new WireStream("/api/mapping/window", (bytes) => {
    if (view.feed(bytes)) stream.send({ type: "resync" });
  });

  const paintLoop = () => {
    if (view.needsPaint && !document.hidden) view.paint();
    requestAnimationFrame(paintLoop);
  };
  requestAnimationFrame(paintLoop);
}
