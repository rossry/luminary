/* Luminary live client: layout over REST, wire bytes over WS, Canvas paint.
 * The WebSocket carries only codec frames — identical to serial (spec §14.3).
 */

import { LumiDecoder, FRAME_KEYFRAME, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";
import { GlowRenderer, oklchToLinear } from "./glow.js";

const el = (id) => document.getElementById(id);

function pointInTriangle(x, y, tri) {
  const [[ax, ay], [bx, by], [cx, cy]] = tri;
  const s1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
  const s2 = (cx - bx) * (y - by) - (cy - by) * (x - bx);
  const s3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx);
  return (s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0);
}

class Client {
  constructor() {
    this.canvas = el("canvas");
    this.ctx = this.canvas.getContext("2d");
    this.buffer = document.createElement("canvas"); // offscreen scene, composited per paint
    this.bufferCtx = this.buffer.getContext("2d");
    this.decoder = null;
    this.layout = null;
    this.ws = null;
    this.paused = false;
    this.bytes = 0;
    this.frames = 0;
    this.windowStart = performance.now();
    this.needsPaint = false;

    // Realistic cloth render (2D view): WebGL2 splatting on a canvas layered
    // *under* this one; seams/scaffold/clicks stay on the 2D canvas on top.
    this.glow = null; // GlowRenderer or null (no WebGL2 -> flat only)
    this.renderMode = "realistic"; // downgraded to "flat" if GL init fails
    this.drag = null;
    this.suppressClick = false;

    el("play").onclick = () => this.play();
    el("render").onclick = () => this.toggleRender();
    this.canvas.onclick = (e) => this.onCanvasClick(e);
    el("pause").onclick = () => this.togglePause();
    el("resync").onclick = () => this.send({ type: "resync" });
    el("pattern").onchange = () => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: "set_pattern", name: el("pattern").value });
      }
    };
    this.loadLists();
    requestAnimationFrame(() => this.paintLoop());
    setInterval(() => this.updateStats(), 500);
  }

  async loadLists() {
    const [lights, patterns] = await Promise.all([
      fetch("/api/lights").then((r) => r.json()),
      fetch("/api/patterns").then((r) => r.json()),
    ]);
    el("lights").innerHTML = lights
      .map((g) => `<option value="${g.id}">${g.name || g.id} (${g.n_lights})</option>`)
      .join("");
    el("pattern").innerHTML = patterns
      .filter((p) => p.ok)
      .map((p) => `<option value="${p.name}">${p.name} — ${p.description}</option>`)
      .join("");
  }

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  async play() {
    const lightsId = el("lights").value;
    const pattern = el("pattern").value;
    if (!lightsId || !pattern) return;
    if (this.ws) this.ws.close();

    this.layout = await fetch(`/api/lights/${lightsId}/layout`).then((r) => r.json());
    this.buildDrawList();
    this.decoder = new LumiDecoder();
    this.bytes = 0;
    this.frames = 0;

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(
      `${proto}//${location.host}/api/play?lights=${lightsId}&pattern=${pattern}&fps=30`
    );
    this.ws.binaryType = "arraybuffer";
    this.ws.onmessage = (event) => {
      const bytes = new Uint8Array(event.data);
      this.bytes += bytes.length;
      const applied = this.decoder.feed(bytes);
      for (const frame of applied) {
        if (frame.type !== FRAME_SESSION) this.frames++;
        this.needsPaint = true;
        this.glowColorsStale = true;
      }
      if (this.decoder.wantResync) {
        this.decoder.wantResync = false;
        this.send({ type: "resync" });
      }
    };
    this.ws.onopen = () => (el("status").textContent = "connected");
    this.ws.onclose = () => (el("status").textContent = "disconnected");
  }

  togglePause() {
    this.paused = !this.paused;
    this.send({ type: this.paused ? "pause" : "resume" });
    el("pause").textContent = this.paused ? "Resume" : "Pause";
  }

  buildDrawList() {
    const [vx, vy, vw, vh] = this.layout.viewBox;
    const canvas = this.canvas;
    canvas.width = canvas.clientWidth * devicePixelRatio;
    canvas.height = canvas.clientHeight * devicePixelRatio;
    this.buffer.width = canvas.width;
    this.buffer.height = canvas.height;
    this.lastColor = null; // reset per-light paint cache (sized after draws)
    const scale = Math.min(canvas.width / vw, canvas.height / vh);
    const ox = (canvas.width - vw * scale) / 2 - vx * scale;
    const oy = (canvas.height - vh * scale) / 2 - vy * scale;
    const tx = (x) => x * scale + ox;
    const ty = (y) => y * scale + oy;

    // Structural overlays (pentagon geometries): the piece is inset
    // cloth+PVC+LED triangles in a metal frame.
    const overlays = this.layout.overlays;
    this.glowSeams = null;
    // Clickable structural triangles: toggle a whole PVC subunit off/on to
    // preview build holes (frontend-only; the wire stream is untouched).
    this.triangles = ((overlays && overlays.triangles) || []).map((tri) =>
      tri.map(([px, py]) => [tx(px), ty(py)])
    );
    // The lit panel is its structural triangle shrunk about the incenter by
    // capture()'s PANEL_INSET_INCHES; overlays.panel ships that affine per
    // triangle as [cx, cy, scale]. The server already applied it to the
    // display polygons — the cloth mask and the LED anchors below have to
    // follow the same map or the beads land outside their own panel.
    const panelAffine = (overlays && overlays.panel) || [];
    this.panelMap = (t, x, y) => {
      const p = panelAffine[t];
      return p ? [p[0] + (x - p[0]) * p[2], p[1] + (y - p[1]) * p[2]] : [x, y];
    };
    this.clothTriangles = ((overlays && overlays.triangles) || []).map((tri, t) =>
      tri.map(([px, py]) => this.panelMap(t, px, py))
    );
    this.offTriangles = new Set();
    if (overlays) {
      const toSeg = (seg) => [tx(seg[0][0]), ty(seg[0][1]), tx(seg[1][0]), ty(seg[1][1])];
      // Physical scale: mean strut = 57.30" (class-count-weighted; keep in
      // sync with _MEAN_STRUT_INCHES in pentagon/adapters.py); calibrate
      // world-units-per-inch against the mean world strut length.
      const frameSegs = overlays.frame || [];
      let meanWorld = 0;
      for (const [a, b] of frameSegs) meanWorld += Math.hypot(b[0] - a[0], b[1] - a[1]);
      meanWorld = frameSegs.length ? meanWorld / frameSegs.length : 57.3;
      const inch = (meanWorld / 57.3) * scale; // device px per physical inch
      // Draw the pipes where they physically are — riding the inset panel,
      // not spanning the full structural triangle. overlays.pvc stays in
      // structural space for the anchor ray-cast below.
      const pvcSegs = (overlays.pvc_panel || overlays.pvc || []).map(toSeg);
      const frame = frameSegs.map(toSeg);
      // Structure is drawn in the realistic render only. Flat cells is the
      // schematic view — bare display polygons, the way it read before the
      // cloth work — so it gets no seams (see the un-inset pass below).
      //
      // At night the structure is just dark, not gray, and
      // cloth in front of a pipe still glows from light scattered in the
      // fabric — so the seams are near-black and semi-transparent, dimming
      // the glow underneath instead of erasing it.
      this.glowSeams = [
        { color: "rgba(10,10,14,0.5)", width: Math.max(1, 1.315 * inch), segs: pvcSegs },
        { color: "rgba(6,6,8,0.6)", width: Math.max(1, 3.0 * inch), segs: frame },
        { color: "#1a1a1f", width: Math.max(1, 1.5 * inch), segs: frame },
      ];
    }

    this.scaffoldPaths = (this.layout.scaffold || []).map((line) => ({
      x1: tx(line.p1[0]), y1: ty(line.p1[1]),
      x2: tx(line.p2[0]), y2: ty(line.p2[1]),
    }));
    this.draws = this.layout.lights.map((light) => {
      if (light.display && light.display.length >= 3) {
        return {
          kind: "poly",
          points: light.display.map(([px, py]) => [tx(px), ty(py)]),
          controller: light.controller, channel: light.channel, index: light.index,
        };
      }
      return {
        kind: "dot",
        x: tx(light.x), y: ty(light.y),
        r: Math.max(2, scale * Math.min(vw, vh) * 0.008),
        controller: light.controller, channel: light.channel, index: light.index,
      };
    });
    this.lastColor = new Float64Array(this.draws.length * 3).fill(NaN);
    // Assign each light to its structural triangle by shape centroid.
    this.lightTri = this.draws.map((d) => {
      let cx, cy;
      if (d.kind === "poly") {
        cx = cy = 0;
        for (const [px, py] of d.points) { cx += px; cy += py; }
        cx /= d.points.length;
        cy /= d.points.length;
      } else {
        cx = d.x; cy = d.y;
      }
      return this.triangles.findIndex((tri) => pointInTriangle(cx, cy, tri));
    });
    // Flat cells draws the structural facet, not the lit panel. The panel
    // affine is a fidelity map for the cloth render; leaving it applied here
    // would open a gap along every seam that the flat view never had. It is
    // invertible and shipped per triangle, so undo it — done after lightTri,
    // which needs the centroids to still be well inside their own triangle.
    if (panelAffine.length) {
      this.draws.forEach((d, i) => {
        const pa = panelAffine[this.lightTri[i]];
        if (!pa || d.kind !== "poly" || !pa[2]) return;
        const cx = tx(pa[0]);
        const cy = ty(pa[1]);
        d.points = d.points.map(([px, py]) => [
          cx + (px - cx) / pa[2],
          cy + (py - cy) / pa[2],
        ]);
      });
    }
    this.proj = { scale, ox, oy };
    this.updateTriCount();
    this.resetScene();
    this.setupGlow();
  }

  /* Build the realistic-render instance list: per LED, the physical strip
   * position (anchor) and unit throw direction, in world coords. The layout
   * serves pos = anchor + half a beam-width forward (the pattern basis
   * point), so the anchor is recovered by casting back along -dir to the
   * nearest structural segment (PVC pipe or frame edge) the strip lines. */
  setupGlow() {
    const btn = el("render");
    const gc = el("glow");
    gc.width = this.canvas.width;
    gc.height = this.canvas.height;
    if (!this.glow) this.glow = GlowRenderer.create(gc);
    if (this.glow && !this.glowLossHooked) {
      // GPU reset / tab eviction kills the GL context at runtime; without
      // these hooks every GL call becomes a silent no-op and the view blanks.
      this.glowLossHooked = true;
      gc.addEventListener("webglcontextlost", (e) => {
        e.preventDefault(); // required for webglcontextrestored to fire
        this.glow = null;
        this.renderMode = "flat";
        btn.textContent = "Cloth glow";
        btn.disabled = true;
        if (this.draws) this.resetScene();
        this.needsPaint = true;
      });
      gc.addEventListener("webglcontextrestored", () => {
        this.glow = null;
        if (this.layout) {
          this.renderMode = "realistic";
          this.setupGlow();
          this.needsPaint = true;
        }
      });
    }
    if (!this.glow) {
      this.renderMode = "flat";
      btn.disabled = true;
      btn.textContent = "Cloth glow";
      btn.title = "WebGL2 unavailable — flat cells only";
      return;
    }
    btn.disabled = false;
    const overlays = this.layout.overlays;
    const segs = []; // [x1,y1,x2,y2, insetWorld, spillScale]
    const frameSegs = (overlays && overlays.frame) || [];
    // Boundary frame edges (owned by a single triangle) have no cloth on
    // the far side — nothing catches spilled light there. Interior edges
    // spill onto the neighboring panel's cloth.
    const ekey = (a, b) => {
      const r = (v) => Math.round(v * 1000);
      const k1 = `${r(a[0])},${r(a[1])}`;
      const k2 = `${r(b[0])},${r(b[1])}`;
      return k1 < k2 ? `${k1}|${k2}` : `${k2}|${k1}`;
    };
    const edgeCount = new Map();
    for (const tri of (overlays && overlays.triangles) || []) {
      for (let i = 0; i < 3; i++) {
        const k = ekey(tri[i], tri[(i + 1) % 3]);
        edgeCount.set(k, (edgeCount.get(k) || 0) + 1);
      }
    }
    // world units per physical inch, from the mean strut length (57.30",
    // class-count-weighted — see seams comment / adapters.py _MEAN_STRUT_INCHES)
    let meanWorld = 0;
    for (const [a, b] of frameSegs) meanWorld += Math.hypot(b[0] - a[0], b[1] - a[1]);
    meanWorld = frameSegs.length ? meanWorld / frameSegs.length : 57.3;
    const wpi = meanWorld / 57.3;
    // Strip standoffs from their baselines: 1.25" at frame seams (measured
    // from a build photo: strips 5.31" apart across a seam, panel inset
    // 1.5", so standoff ≈ one pipe OD), ~pipe radius on interior spokes
    // (eyeballed).
    for (const [a, b] of (overlays && overlays.pvc) || [])
      segs.push([a[0], a[1], b[0], b[1], 0.8 * wpi, 1]);
    for (const [a, b] of frameSegs)
      segs.push([a[0], a[1], b[0], b[1], 1.25 * wpi, edgeCount.get(ekey(a, b)) >= 2 ? 1 : 0]);
    const maxBack = 6 * wpi; // anchors sit well under half a beam-width away
    const inst = new Float32Array(this.layout.lights.length * 5);
    this.layout.lights.forEach((light, i) => {
      let ax = light.x;
      let ay = light.y;
      let dx = 0;
      let dy = 0;
      let spill = 1;
      if (light.dir) {
        dx = light.dir[0];
        dy = light.dir[1];
        let best = Infinity;
        let inset = 0;
        for (const [sx1, sy1, sx2, sy2, segInset, segSpill] of segs) {
          // ray (pos, -dir) vs segment; smallest forward hit is the baseline
          const rx = -dx, ry = -dy;
          const ex = sx2 - sx1, ey = sy2 - sy1;
          const den = rx * ey - ry * ex;
          if (Math.abs(den) < 1e-9) continue;
          const qx = sx1 - ax, qy = sy1 - ay;
          const t = (qx * ey - qy * ex) / den;
          const u = (qx * ry - qy * rx) / den;
          if (t >= 0 && t <= maxBack && u >= -0.001 && u <= 1.001 && t < best) {
            best = t;
            inset = segInset;
            spill = segSpill;
          }
        }
        if (best < Infinity) {
          const back = Math.max(0, best - inset);
          ax -= dx * back;
          ay -= dy * back;
        }
      }
      // Strips ride the panel, so they shrink with it (see panelMap).
      const t = this.lightTri[i];
      if (t >= 0) [ax, ay] = this.panelMap(t, ax, ay);
      inst[i * 5] = ax;
      inst[i * 5 + 1] = ay;
      inst[i * 5 + 2] = dx;
      inst[i * 5 + 3] = dy;
      inst[i * 5 + 4] = spill;
    });
    this.glow.setLights(inst, wpi);
    this.glow.setTransform(this.proj.scale, this.proj.ox, this.proj.oy);
    this.glowColorsStale = true;
  }

  toggleRender() {
    if (!this.glow) return;
    this.renderMode = this.renderMode === "realistic" ? "flat" : "realistic";
    el("render").textContent = this.renderMode === "realistic" ? "Flat cells" : "Cloth glow";
    this.glowColorsStale = true;
    if (this.renderMode === "flat" && this.draws) {
      this.resetScene(); // buffer was idle while GL rendered; rebuild fully
    }
    this.needsPaint = true;
  }

  onCanvasClick(e) {
    if (this.suppressClick) {
      this.suppressClick = false;
      return;
    }
    if (!this.triangles || !this.triangles.length || !this.draws) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (this.canvas.width / rect.width);
    const y = (e.clientY - rect.top) * (this.canvas.height / rect.height);
    const hit = this.triangles.findIndex((tri) => pointInTriangle(x, y, tri));
    if (hit < 0) return;
    if (this.offTriangles.has(hit)) this.offTriangles.delete(hit);
    else this.offTriangles.add(hit);
    // Force the subunit's lights to repaint under their new on/off state.
    for (let i = 0; i < this.draws.length; i++) {
      if (this.lightTri[i] === hit) this.lastColor[i * 3] = NaN;
    }
    this.glowColorsStale = true;
    this.updateTriCount();
    this.needsPaint = true;
  }

  updateTriCount() {
    const total = this.triangles ? this.triangles.length : 0;
    el("tricount").textContent = total
      ? `${total - this.offTriangles.size}/${total} triangles on`
      : "";
  }

  resetScene() {
    const ctx = this.bufferCtx;
    ctx.fillStyle = "#101014";
    ctx.fillRect(0, 0, this.buffer.width, this.buffer.height);
    ctx.strokeStyle = "#2c2c34";
    ctx.lineWidth = 1.5 * devicePixelRatio;
    for (const s of this.scaffoldPaths || []) {
      ctx.beginPath();
      ctx.moveTo(s.x1, s.y1);
      ctx.lineTo(s.x2, s.y2);
      ctx.stroke();
    }
    if (this.lastColor) this.lastColor.fill(NaN);
  }

  paintLoop() {
    // Realistic mode repaints every frame (~0.2 ms): glow.params stays
    // live-tunable from the console even when the stream is paused.
    if (this.renderMode === "realistic" && this.glow && this.draws)
      this.needsPaint = true;
    if (this.needsPaint && !document.hidden) {
      this.needsPaint = false;
      this.paint();
    }
    requestAnimationFrame(() => this.paintLoop());
  }

  paint() {
    if (this.renderMode === "realistic" && this.glow && this.draws) {
      this.paintGlow();
      return;
    }
    // The scene lives in a persistent offscreen buffer; each paint fills only
    // the lights whose quantized color changed since they were last drawn
    // (frames are budget-capped deltas, so that's typically a small fraction),
    // then composites the buffer in one drawImage.
    this.updateScene();
    this.ctx.drawImage(this.buffer, 0, 0);
  }

  /* Realistic path: linear-light splatting on the GL canvas underneath;
   * this canvas is cleared to transparent and keeps only the structure
   * strokes (PVC + frame), which read as the dark seams they are. */
  paintGlow() {
    if (this.glowColorsStale) {
      this.updateGlowColors();
      this.glowColorsStale = false;
    }
    // Cloth coverage: the throw/spill only exist where cloth catches them —
    // not past the lit panel's edge (inset from the frame, see panelMap), not
    // on killed panels.
    const tris = this.clothTriangles || [];
    if (tris.length) {
      const verts = new Float32Array(tris.length * 6);
      let k = 0;
      tris.forEach((tri, t) => {
        if (this.offTriangles.has(t)) return;
        for (const [px, py] of tri) {
          verts[k++] = px;
          verts[k++] = py;
        }
      });
      this.glow.setTriangles(verts.subarray(0, k));
    } else {
      this.glow.setTriangles(null);
    }
    this.glow.render();
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.strokeSeams(ctx, this.glowSeams);
  }

  updateGlowColors() {
    const cols = this.glow.colors;
    if (!cols) return;
    cols.fill(0);
    if (this.decoder) {
      const strips = new Map();
      for (let i = 0; i < this.draws.length; i++) {
        const d = this.draws[i];
        if (this.lightTri[i] >= 0 && this.offTriangles.has(this.lightTri[i])) continue;
        const key = `${d.controller}:${d.channel}`;
        if (!strips.has(key)) {
          try {
            strips.set(key, this.decoder.stripOKLCH(d.controller, d.channel));
          } catch {
            strips.set(key, null);
          }
        }
        const strip = strips.get(key);
        if (strip && d.index * 3 + 2 < strip.length) {
          oklchToLinear(
            strip[d.index * 3],
            strip[d.index * 3 + 1],
            strip[d.index * 3 + 2],
            cols,
            i * 3
          );
        }
      }
    }
    this.glow.markColors();
  }

  strokeSeams(ctx, seams) {
    if (!seams) return;
    ctx.lineCap = "round";
    for (const cls of seams) {
      ctx.strokeStyle = cls.color;
      ctx.lineWidth = cls.width;
      ctx.beginPath();
      for (const [x1, y1, x2, y2] of cls.segs) {
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
      }
      ctx.stroke();
    }
  }

  updateScene() {
    if (!this.decoder || !this.draws || !this.lastColor) return 0;
    const ctx = this.bufferCtx;
    let repainted = 0;

    // Decode each strip once, then color lights by (controller, channel, index).
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
      let L = -1, C = -1, H = -1; // sentinel: strip missing → paint "#222" once
      if (strip && d.index * 3 + 2 < strip.length) {
        L = strip[d.index * 3];
        C = strip[d.index * 3 + 1];
        H = strip[d.index * 3 + 2];
      }
      if (this.lightTri[i] >= 0 && this.offTriangles.has(this.lightTri[i])) {
        L = -2; C = -2; H = -2; // subunit clicked off: unlit panel, painted once
      }
      const j = i * 3;
      const last = this.lastColor;
      if (last[j] === L && last[j + 1] === C && last[j + 2] === H) continue;
      repainted++;
      last[j] = L;
      last[j + 1] = C;
      last[j + 2] = H;
      let fill = L === -2 ? "#0e0e12" : "#222";
      if (L >= 0) {
        const [r, g, b] = oklchToSrgb8(L, C, H);
        fill = `rgb(${r},${g},${b})`;
      }
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
    return repainted;
  }

  updateStats() {
    const now = performance.now();
    const dt = (now - this.windowStart) / 1000;
    if (dt <= 0) return;
    const fps = this.frames / dt;
    const rate = this.bytes / dt;
    const nActive = this.layout ? this.layout.counts.active : 0;
    const perLight = this.frames && nActive ? this.bytes / this.frames / nActive : 0;
    el("stats").textContent =
      `${fps.toFixed(1)} fps · ${(rate / 1024).toFixed(1)} KiB/s · ` +
      `${perLight.toFixed(2)} B/light·frame`;
    this.frames = 0;
    this.bytes = 0;
    this.windowStart = now;
  }
}

window.client = new Client(); // exposed for debugging/perf probes
