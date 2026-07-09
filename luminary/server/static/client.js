/* Luminary live client: layout over REST, wire bytes over WS, Canvas paint.
 * The WebSocket carries only codec frames — identical to serial (spec §14.3).
 */

import { LumiDecoder, FRAME_KEYFRAME, FRAME_SESSION } from "./decoder.js";
import { oklchToSrgb8 } from "./color.js";

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

    el("play").onclick = () => this.play();
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
  }

  paintLoop() {
    if (this.needsPaint && !document.hidden) {
      this.needsPaint = false;
      this.paint();
    }
    requestAnimationFrame(() => this.paintLoop());
  }

  paint() {
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

new Client();
