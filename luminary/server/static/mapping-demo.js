/* Mapping tutorial (plan/mapping/DESCRIPTION.md, web adapter).
 *
 * TOP: a mockup of the physical build — the WIRE stream decoded and placed
 * through a deliberately scrambled ground truth (/api/mapping/demo-truth),
 * so the "sphere" responds the way a really-miswired build would.
 * BOTTOM: the same base-station window as mapping.html. Same keys, same
 * state machine, zero hardware.
 *
 * The mockup paints through the plan's serpentine strip references: for
 * each physical strip, decoded LED i lands on the panel's reference net
 * light for path position i under the panel's *physical* winding and
 * density — the very same net-light bridge the wire renderer uses
 * (SessionCore.strip_refs), so the mockup cannot diverge from the
 * window's idea of the sphere. Stream indices past the transmitted
 * length are unfed LEDs and contribute black; cells fed by two LEDs
 * (a 360 strip over 180 reference lights) average them.
 */

import {
  StreamView, WireStream, ControlChannel, Hud,
  fitTransform, buildDraws, fillDraw, BASE,
} from "./mapping.js";
import { LumiDecoder, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";

const UNLIT = "#141419"; // an unfed panel is dark cloth, not a hole

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

    // Serpentine references by tri_index, straight from the plan JSON
    // (indices into layout.lights == draw indices).
    const refs = new Map();
    for (const panels of Object.values(plan.panels)) {
      for (const p of panels) refs.set(p.tri_index, p.refs);
    }
    // The scrambled wiring: which physical panel each (controller, channel)
    // actually drives, and how that panel is physically built. The server
    // serves refs per density AND winding, so no index logic lives here.
    this.wiring = [];
    for (const [cid, board] of Object.entries(truth.boards)) {
      for (const [ch, p] of Object.entries(board.channels)) {
        this.wiring.push({
          cid: Number(cid), ch: Number(ch),
          refs: refs.get(p.tri_index)[String(p.density)][p.winding],
          density: p.density,
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
    const n = this.draws.length;
    const sums = new Float64Array(n * 3);
    const counts = new Uint32Array(n);
    for (const w of this.wiring) {
      let strip = null;
      try {
        strip = this.decoder.stripOKLCH(w.cid, w.ch);
      } catch {
        // this controller/channel has no stream yet → panel stays unlit
        continue;
      }
      const fed = strip.length / 3;
      for (let i = 0; i < w.density; i++) {
        const cell = w.refs[i];
        counts[cell]++;
        if (i < fed) {
          const [r, g, b] = oklchToSrgb8(
            strip[i * 3], strip[i * 3 + 1], strip[i * 3 + 2]
          );
          sums[cell * 3] += r;
          sums[cell * 3 + 1] += g;
          sums[cell * 3 + 2] += b;
        } // else: no data for this LED → black
      }
    }
    const ctx = this.ctx;
    for (let cell = 0; cell < n; cell++) {
      if (!counts[cell]) continue;
      const r = Math.round(sums[cell * 3] / counts[cell]);
      const g = Math.round(sums[cell * 3 + 1] / counts[cell]);
      const b = Math.round(sums[cell * 3 + 2] / counts[cell]);
      const fill = `rgb(${r},${g},${b})`;
      if (this.lastFill[cell] === fill) continue;
      this.lastFill[cell] = fill;
      fillDraw(ctx, this.draws[cell], fill);
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
