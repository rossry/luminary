/* Luminary live client: layout over REST, wire bytes over WS, Canvas paint.
 * The WebSocket carries only codec frames — identical to serial (spec §14.3).
 *
 * Two render modes for the 2D view:
 *   - "realistic" (default when WebGL2 is available): physically-motivated
 *     cloth render — see glow.js. The GL canvas sits under this one; this
 *     canvas keeps the structural seam strokes on top.
 *   - "flat": schematic per-light cell fill (also the no-WebGL2 fallback).
 */

import { LumiDecoder, FRAME_KEYFRAME, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";
import { GlowRenderer, oklchToLinear } from "./glow.js";

const el = (id) => document.getElementById(id);

class Client {
  constructor() {
    this.canvas = el("canvas");
    this.ctx = this.canvas.getContext("2d");
    this.decoder = null;
    this.layout = null;
    this.ws = null;
    this.paused = false;
    this.bytes = 0;
    this.frames = 0;
    this.windowStart = performance.now();
    this.needsPaint = false;
    this.glow = null; // GlowRenderer, or null when WebGL2 is unavailable
    this.renderMode = "realistic"; // downgraded to "flat" if GL init fails
    this.scatter = 0; // cloth slider: extra fabric scatter, inches

    el("play").onclick = () => this.play();
    el("render").onclick = () => this.toggleRender();
    el("cloth").oninput = () => {
      this.scatter = +el("cloth").value / 8;
      el("cloth-label").textContent = this.scatter
        ? `cloth +${this.scatter.toFixed(2)}″`
        : "cloth thin";
      this.needsPaint = true;
    };
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
    const scale = Math.min(canvas.width / vw, canvas.height / vh);
    const ox = (canvas.width - vw * scale) / 2 - vx * scale;
    const oy = (canvas.height - vh * scale) / 2 - vy * scale;
    const tx = (x) => x * scale + ox;
    const ty = (y) => y * scale + oy;
    this.proj = { scale, ox, oy };

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
    this.setupGlow();
  }

  /* Build the realistic-render instance list: per LED, the physical strip
   * position (anchor) and unit throw direction, in world coords. The layout
   * serves pos = anchor + half a beam-width forward (the pattern basis
   * point, spec §7.3.1), so the anchor is recovered by casting back along
   * -dir to the nearest structural segment (PVC pipe or frame edge) the
   * strip lines, then insetting by the physical mount offset. */
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
        this.needsPaint = true;
      });
      gc.addEventListener("webglcontextrestored", () => {
        this.glow = null;
        if (this.layout) {
          this.renderMode = "realistic";
          this.setupGlow();
          this.glowColorsStale = true;
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
    btn.textContent = this.renderMode === "realistic" ? "Flat cells" : "Cloth glow";
    const overlays = this.layout.overlays;
    const frameSegs = (overlays && overlays.frame) || [];
    // world units per physical inch, from the mean strut length (50.25–59.375",
    // mean 54.8125")
    let meanWorld = 0;
    for (const [a, b] of frameSegs) meanWorld += Math.hypot(b[0] - a[0], b[1] - a[1]);
    meanWorld = frameSegs.length ? meanWorld / frameSegs.length : 54.8125;
    const wpi = meanWorld / 54.8125;

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
    // Strips mount inset from their baseline: the cloth panel edge sits ~2"
    // inside the metal frame, and PVC pipes carry strips at their surface
    // (~pipe radius). The bead rows must flank the dark seams, not sit on
    // them. segs: [x1, y1, x2, y2, insetWorld, spillScale]
    const segs = [];
    for (const [a, b] of (overlays && overlays.pvc) || [])
      segs.push([a[0], a[1], b[0], b[1], 0.8 * wpi, 1]);
    for (const [a, b] of frameSegs)
      segs.push([a[0], a[1], b[0], b[1], 2.0 * wpi, edgeCount.get(ekey(a, b)) >= 2 ? 1 : 0]);
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
      inst[i * 5] = ax;
      inst[i * 5 + 1] = ay;
      inst[i * 5 + 2] = dx;
      inst[i * 5 + 3] = dy;
      inst[i * 5 + 4] = spill;
    });
    this.glow.setLights(inst, wpi);
    this.glow.setTransform(this.proj.scale, this.proj.ox, this.proj.oy);
    this.glowColorsStale = true;

    // Cloth coverage: throw/spill only exist where cloth catches them —
    // in particular, not past the outermost frame edges.
    const tris = (overlays && overlays.triangles) || [];
    if (tris.length) {
      const verts = new Float32Array(tris.length * 6);
      let k = 0;
      for (const tri of tris)
        for (const [px, py] of tri) {
          verts[k++] = px;
          verts[k++] = py;
        }
      this.glow.setTriangles(verts);
    } else {
      this.glow.setTriangles(null);
    }

    // Structure overlay, stroked on this canvas over the glow. At night the
    // metal is just dark, and cloth in front of a pipe still glows from
    // light scattered in the fabric — near-black, semi-transparent.
    const inch = wpi * this.proj.scale; // device px per physical inch
    const seg2 = (seg) => [
      seg[0][0] * this.proj.scale + this.proj.ox,
      seg[0][1] * this.proj.scale + this.proj.oy,
      seg[1][0] * this.proj.scale + this.proj.ox,
      seg[1][1] * this.proj.scale + this.proj.oy,
    ];
    const pvcSegs = ((overlays && overlays.pvc) || []).map(seg2);
    const frame = frameSegs.map(seg2);
    this.glowSeams = [
      { color: "rgba(10,10,14,0.5)", width: Math.max(1, 1.315 * inch), segs: pvcSegs },
      { color: "rgba(6,6,8,0.6)", width: Math.max(1, 3.0 * inch), segs: frame },
      { color: "#1a1a1f", width: Math.max(1, 1.5 * inch), segs: frame },
    ];
  }

  toggleRender() {
    if (!this.glow) return;
    this.renderMode = this.renderMode === "realistic" ? "flat" : "realistic";
    el("render").textContent = this.renderMode === "realistic" ? "Flat cells" : "Cloth glow";
    this.needsPaint = true;
  }

  paintLoop() {
    // Realistic mode repaints every frame (~0.2 ms on the GPU): glow.params
    // stays live-tunable from the console even when the stream is paused.
    if (this.renderMode === "realistic" && this.glow && this.draws) this.needsPaint = true;
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
    const ctx = this.ctx;
    ctx.fillStyle = "#101014";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.strokeStyle = "#2c2c34";
    ctx.lineWidth = 1.5 * devicePixelRatio;
    for (const s of this.scaffoldPaths || []) {
      ctx.beginPath();
      ctx.moveTo(s.x1, s.y1);
      ctx.lineTo(s.x2, s.y2);
      ctx.stroke();
    }
    if (!this.decoder || !this.draws) return;

    // Decode each strip once, then color lights by (controller, channel, index).
    const strips = new Map();
    for (const d of this.draws) {
      const key = `${d.controller}:${d.channel}`;
      if (!strips.has(key)) {
        try {
          strips.set(key, this.decoder.stripOKLCH(d.controller, d.channel));
        } catch {
          strips.set(key, null);
        }
      }
      const strip = strips.get(key);
      let fill = "#222";
      if (strip && d.index * 3 + 2 < strip.length) {
        const [r, g, b] = oklchToSrgb8(
          strip[d.index * 3], strip[d.index * 3 + 1], strip[d.index * 3 + 2]
        );
        fill = `rgb(${r},${g},${b})`;
      }
      ctx.fillStyle = fill;
      if (d.kind === "poly") {
        ctx.beginPath();
        ctx.moveTo(d.points[0][0], d.points[0][1]);
        for (let i = 1; i < d.points.length; i++) ctx.lineTo(d.points[i][0], d.points[i][1]);
        ctx.closePath();
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  }

  /* Realistic path: linear-light splatting on the GL canvas underneath;
   * this canvas is cleared to transparent and keeps only the structure
   * strokes (PVC + frame), which read as the dark seams they are. */
  paintGlow() {
    if (this.glowColorsStale) {
      this.updateGlowColors();
      this.glowColorsStale = false;
    }
    this.glow.params.scatterIn = this.scatter;
    this.glow.render();
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.glowSeams) return;
    ctx.lineCap = "round";
    for (const cls of this.glowSeams) {
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

  updateGlowColors() {
    const cols = this.glow.colors;
    if (!cols) return;
    cols.fill(0);
    if (this.decoder) {
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

window.client = new Client(); // exposed for console tuning (client.glow.params)
