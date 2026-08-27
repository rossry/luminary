/* Mapping tutorial (plan/mapping/DESCRIPTION.md, web adapter).
 *
 * TOP: a mockup of the physical build — the WIRE stream decoded and placed
 * through a deliberately scrambled ground truth (/api/mapping/demo-truth),
 * so the "sphere" responds the way a really-miswired build would.
 * BOTTOM: the same base-station window as mapping.html. Same keys, same
 * state machine, zero hardware.
 *
 * Mockup approximation (training aid, not a simulator): each physical
 * panel is painted per angular sector about its six-red corner — the mean
 * decoded sRGB of the wire strip's LEDs that land in that sector under the
 * panel's *physical* winding and density (the angular strip model of
 * session.py). Stream indices past the transmitted length are unfed LEDs
 * and contribute black; per-LED serpentine detail is intentionally lost.
 */

import {
  StreamView, WireStream, ControlChannel, Hud,
  fitTransform, buildDraws, fillDraw, BASE,
} from "./mapping.js";
import { LumiDecoder, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";

const SECTORS = 48; // angular buckets per panel; plenty for the band test
const UNLIT = "#141419"; // an unfed panel is dark cloth, not a hole

function sectorFills(strip, density, winding, K) {
  const sums = new Float64Array(K * 3);
  const counts = new Uint32Array(K);
  const n = strip ? strip.length / 3 : 0;
  const fills = new Array(K).fill(UNLIT);
  for (let i = 0; i < density; i++) {
    let f = (i + 0.5) / density; // arc fraction from the six-red corner
    if (winding === "cw") f = 1 - f;
    const k = Math.min(K - 1, Math.floor(f * K));
    counts[k]++;
    if (i < n) {
      const [r, g, b] = oklchToSrgb8(strip[i * 3], strip[i * 3 + 1], strip[i * 3 + 2]);
      sums[k * 3] += r;
      sums[k * 3 + 1] += g;
      sums[k * 3 + 2] += b;
    } // else: no data for this LED → black
  }
  for (let k = 0; k < K; k++) {
    if (!counts[k]) continue;
    const r = Math.round(sums[k * 3] / counts[k]);
    const g = Math.round(sums[k * 3 + 1] / counts[k]);
    const b = Math.round(sums[k * 3 + 2] / counts[k]);
    fills[k] = `rgb(${r},${g},${b})`;
  }
  return fills;
}

class BuildMockup {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.decoder = new LumiDecoder();
    this.draws = null;
    this.needsPaint = false;
  }

  setLayout(layout, plan, truth) {
    this.t = fitTransform(this.canvas, layout.viewBox);
    const built = buildDraws(layout, this.t);
    this.draws = built.draws;
    this.frameSegs = built.frame;

    // Panel arc metadata by tri_index, from the plan JSON.
    const meta = new Map();
    for (const panels of Object.values(plan.panels)) {
      for (const p of panels) {
        meta.set(p.tri_index, { corner: p.corner_xy, a0: p.arc.a0, span: p.arc.span });
      }
    }
    // Group draws per panel; each draw's sector along the panel's arc is
    // fixed by geometry (world coords — layout.lights carries them).
    const wrap = (x) => Math.atan2(Math.sin(x), Math.cos(x));
    this.panelDraws = new Map();
    built.lightTri.forEach((tri, i) => {
      const m = meta.get(tri);
      if (!m) return;
      const light = layout.lights[i];
      const a = Math.atan2(light.y - m.corner[1], light.x - m.corner[0]);
      const frac = Math.min(0.999, Math.max(0, wrap(a - m.a0) / m.span));
      if (!this.panelDraws.has(tri)) this.panelDraws.set(tri, []);
      this.panelDraws.get(tri).push({ draw: i, sector: Math.floor(frac * SECTORS) });
    });

    // The scrambled wiring: which physical panel each (controller, channel)
    // actually drives, and how that panel is physically built.
    this.wiring = [];
    for (const [cid, board] of Object.entries(truth.boards)) {
      for (const [ch, p] of Object.entries(board.channels)) {
        this.wiring.push({
          cid: Number(cid), ch: Number(ch),
          tri: p.tri_index, winding: p.winding, density: p.density,
        });
      }
    }
    this.resetScene();
  }

  resetScene() {
    const ctx = this.ctx;
    ctx.fillStyle = "#101014";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.lastFill = new Array(this.draws.length).fill(UNLIT);
    for (const d of this.draws) fillDraw(ctx, d, UNLIT);
    ctx.strokeStyle = "#26262e";
    ctx.lineWidth = 1.5 * devicePixelRatio;
    ctx.beginPath();
    for (const [x1, y1, x2, y2] of this.frameSegs) {
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
    }
    ctx.stroke();
    this.needsPaint = true;
  }

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
    for (const w of this.wiring) {
      let strip = null;
      try {
        strip = this.decoder.stripOKLCH(w.cid, w.ch);
      } catch {
        // this controller/channel has no stream yet → panel stays unlit
      }
      const fills = sectorFills(strip, w.density, w.winding, SECTORS);
      for (const { draw, sector } of this.panelDraws.get(w.tri) || []) {
        const fill = fills[sector];
        if (this.lastFill[draw] === fill) continue;
        this.lastFill[draw] = fill;
        fillDraw(ctx, this.draws[draw], fill);
      }
    }
  }
}

const el = (id) => document.getElementById(id);

async function init() {
  const [meta, truthRes] = await Promise.all([
    fetch(new URL("api/mapping/layout", BASE)).then((r) => r.json()),
    fetch(new URL("api/mapping/demo-truth", BASE)),
  ]);
  if (!truthRes.ok) {
    el("overlay-title").textContent = "demo unavailable";
    el("overlay-body").innerHTML =
      "This server has no scrambled demo build. Start the tutorial with " +
      "<code>python -m luminary.mapping.web</code> and open /demo there.";
    el("start").hidden = true;
    return;
  }
  const truth = await truthRes.json();

  const build = new BuildMockup(el("build-canvas"));
  build.setLayout(meta.layout, meta.plan, truth);
  const win = new StreamView(el("window-canvas"));
  win.setLayout(meta.layout);
  const hud = new Hud(el("hud"), el("progress"));
  hud.render(meta.state);

  const wire = new WireStream("api/mapping/wire", (bytes) => {
    if (build.feed(bytes)) wire.send({ type: "resync" });
  });
  const windowStream = new WireStream(
    "api/mapping/window",
    (bytes) => {
      if (win.feed(bytes)) windowStream.send({ type: "resync" });
    },
    (status) => (el("status").textContent = status)
  );

  const paintLoop = () => {
    if (!document.hidden) {
      if (build.needsPaint) build.paint();
      if (win.needsPaint) win.paint();
    }
    requestAnimationFrame(paintLoop);
  };
  requestAnimationFrame(paintLoop);

  // Controls arm only once the overlay is dismissed, so reading the
  // instructions can't accidentally drive the state machine.
  el("start").addEventListener("click", () => {
    el("overlay").remove();
    const control = new ControlChannel((s) => hud.render(s));
    control.bindKeys(window);
    control.bindButtons(document);
  });
}

init();
