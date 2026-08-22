/* Realistic cloth render: WebGL2 additive splatting in linear light.
 *
 * Physical model (from the 2024 panel photo): LED strips line the PVC pipes
 * and the frame, facing into each facet, and the whole apparatus is wrapped
 * in white cloth. Each LED paints the cloth with
 *   - a "bead": tight near-field hotspot directly over the LED,
 *   - a "throw": forward lobe grazing across the cell,
 *     cos^m(theta) / (r^2 + h^2) for a strip standoff h,
 *   - a faint isotropic "spill": light leaking over the pipe (the glowing
 *     rim outside the panel edges in the photo).
 * Light accumulates additively into RGBA16F targets (light adds linearly;
 * blurring gamma pixels is what made the old render muddy), then one
 * hue-preserving tone map + sRGB encode. Beads render at full resolution;
 * the smooth throw accumulates at quarter resolution and upsamples
 * bilinearly, which bounds overdraw.
 *
 * All PSF distances are in physical inches: the client passes world-units-
 * per-inch and a world->device-px transform that matches the 2D canvas.
 */

const VS_SPLAT = `#version 300 es
layout(location=0) in vec2 aCorner;
layout(location=1) in vec2 aAnchor;
layout(location=2) in vec2 aDir;
layout(location=3) in vec3 aColor;
layout(location=4) in float aSpill;
uniform float uScale;     // device px per world unit
uniform vec2 uOffset;     // device px
uniform vec2 uCanvasPx;   // full-res canvas size, device px
uniform float uRadius;    // splat half-size, world units
uniform float uForward;   // splat center shift along aDir, world units
out vec2 vOffs;           // world offset from the LED anchor
out vec2 vDir;
out vec3 vColor;
out float vSpill;
void main() {
  vec2 world = aAnchor + aDir * uForward + aCorner * uRadius;
  vOffs = world - aAnchor;
  vDir = aDir;
  vColor = aColor;
  vSpill = aSpill;
  vec2 px = world * uScale + uOffset;
  gl_Position = vec4(px.x / uCanvasPx.x * 2.0 - 1.0,
                     1.0 - px.y / uCanvasPx.y * 2.0, 0.0, 1.0);
}`;

const FS_BEAD = `#version 300 es
precision highp float;
in vec2 vOffs; in vec2 vDir; in vec3 vColor; in float vSpill;
uniform float uSigma2;    // bead variance, world^2
uniform float uBeadGain;
out vec4 o;
void main() {
  float r2 = dot(vOffs, vOffs);
  o = vec4(vColor * (uBeadGain * exp(-0.5 * r2 / uSigma2)), 0.0);
}`;

const FS_THROW = `#version 300 es
precision highp float;
in vec2 vOffs; in vec2 vDir; in vec3 vColor; in float vSpill;
uniform float uH2;        // strip standoff squared, world^2
uniform float uM;         // forward lobe exponent
uniform float uThrowGain;
uniform float uSpillGain;
uniform float uRange;     // throw fade-out radius, world units
uniform float uSpillRange; // spill dies much sooner: cloth right at the pipe
out vec4 o;
void main() {
  float r2 = dot(vOffs, vOffs);
  float r = sqrt(r2);
  float c = r > 1e-4 ? dot(vOffs, vDir) / r : 0.0;
  float lobe = pow(max(c, 0.0), uM);
  float fall = 1.0 / (r2 + uH2);
  float wT = 1.0 - smoothstep(uRange * 0.6, uRange, r);
  float wS = 1.0 - smoothstep(uSpillRange * 0.5, uSpillRange, r);
  o = vec4(vColor * ((uThrowGain * lobe * wT + uSpillGain * vSpill * wS) * fall), 0.0);
}`;

const VS_MASK = `#version 300 es
layout(location=0) in vec2 aPos;  // world
uniform float uScale; uniform vec2 uOffset; uniform vec2 uCanvasPx;
void main() {
  vec2 px = aPos * uScale + uOffset;
  gl_Position = vec4(px.x / uCanvasPx.x * 2.0 - 1.0,
                     1.0 - px.y / uCanvasPx.y * 2.0, 0.0, 1.0);
}`;

const FS_MASK = `#version 300 es
precision highp float;
out vec4 o;
void main() { o = vec4(1.0); }`;

const VS_TONE = `#version 300 es
out vec2 vUV;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUV = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const FS_TONE = `#version 300 es
precision highp float;
in vec2 vUV;
uniform sampler2D uBead;
uniform sampler2D uThrow;
uniform sampler2D uMask;  // cloth coverage: light exists only on cloth
uniform float uExposure;
uniform vec3 uBg;         // background, linear
out vec4 o;
vec3 srgbEncode(vec3 c) {
  vec3 hi = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
  vec3 lo = 12.92 * c;
  return mix(hi, lo, vec3(lessThanEqual(c, vec3(0.0031308))));
}
void main() {
  vec3 c = (texture(uBead, vUV).rgb + texture(uThrow, vUV).rgb) * texture(uMask, vUV).r;
  c = c * uExposure + uBg;
  // Hue-preserving shoulder: to the eye the cores stayed saturated red (the
  // camera clipped to white; we shouldn't). Compress the max channel toward
  // 1 and scale RGB together so hue and saturation survive.
  float m = max(c.r, max(c.g, c.b));
  const float k = 0.75;
  if (m > k) c *= (k + (1.0 - k) * tanh((m - k) / (1.0 - k))) / m;
  c = clamp(c, 0.0, 1.0);
  float dither = (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;
  o = vec4(srgbEncode(c) + dither, 1.0);
}`;

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(sh));
  }
  return sh;
}

function link(gl, vsSrc, fsSrc) {
  const prog = gl.createProgram();
  gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, vsSrc));
  gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, fsSrc));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(prog));
  }
  return prog;
}

/* OKLCH -> linear sRGB (no gamma encode; the shader encodes after summing).
 * Same OKLab math as color.js; kept here because color.js is the strict
 * mirror of color/convert.py and this variant is display-only. */
export function oklchToLinear(L, C, Hdeg, out, at) {
  const h = (Hdeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;
  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  out[at] = r > 0 ? r : 0;
  out[at + 1] = g > 0 ? g : 0;
  out[at + 2] = bb > 0 ? bb : 0;
}

export class GlowRenderer {
  static create(canvas) {
    try {
      const r = new GlowRenderer(canvas);
      return r.ok ? r : null;
    } catch {
      return null;
    }
  }

  constructor(canvas) {
    this.ok = false;
    this.canvas = canvas;
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: false });
    if (!gl || !gl.getExtension("EXT_color_buffer_float")) return;
    this.gl = gl;
    this.progBead = link(gl, VS_SPLAT, FS_BEAD);
    this.progThrow = link(gl, VS_SPLAT, FS_THROW);
    this.progTone = link(gl, VS_TONE, FS_TONE);
    this.progMask = link(gl, VS_MASK, FS_MASK);

    this.quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW
    );
    this.instBuf = gl.createBuffer(); // [ax, ay, dx, dy, spill] per light, static
    this.colorBuf = gl.createBuffer(); // [r, g, b] linear per light, dynamic
    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 20, 0);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 20, 8);
    gl.vertexAttribDivisor(2, 1);
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, 20, 16);
    gl.vertexAttribDivisor(4, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuf);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 3, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(3, 1);
    gl.bindVertexArray(null);

    this.maskBuf = gl.createBuffer(); // active cloth triangles, world coords
    this.maskVao = gl.createVertexArray();
    gl.bindVertexArray(this.maskVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.maskBuf);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
    this.maskVerts = 0;
    this.haveMask = false;

    this.n = 0;
    this.colors = null;
    this.colorsDirty = false;
    this.wpi = 1; // world units per physical inch
    this.transform = null;
    this.fbBead = null;
    this.fbThrow = null;
    this.texW = 0;
    this.texH = 0;
    // PSF parameters, physical inches / linear gains. Calibrated against the
    // 2024 panel photo (bright beady rims, glow decaying toward a dimmer
    // cell center, faint spill outside the pipes).
    this.params = {
      standoffIn: 1.0, // LED-to-cloth height: sets grazing falloff
      sigmaIn: 0.8, // bead width
      lobeM: 2.0, // forward exponent: LED cosine x grazing incidence
      rangeIn: 38.0, // throw fade-out radius
      spillRangeIn: 15.0, // spill: faint rim just past the pipe, then gone
      beadGain: 10.0,
      throwGain: 5.0,
      spillGain: 0.4,
      exposure: 0.1,
      bg: [0.00518, 0.00518, 0.007], // #101014 sRGB-decoded to linear
    };
    this.ok = true;
  }

  /* inst: Float32Array n*5 of [anchorX, anchorY, dirX, dirY, spillScale]
   * (world coords; anchor = LED position on the strip, dir = unit throw
   * direction or 0,0; spillScale 0 kills spill where no cloth catches it). */
  setLights(inst, wpi) {
    const gl = this.gl;
    this.n = inst.length / 5;
    this.wpi = wpi;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf);
    gl.bufferData(gl.ARRAY_BUFFER, inst, gl.STATIC_DRAW);
    this.colors = new Float32Array(this.n * 3);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.colors, gl.DYNAMIC_DRAW);
    this.colorsDirty = true;
  }

  /* World -> device px, identical to the 2D canvas: px = world*scale+offset. */
  setTransform(scale, ox, oy) {
    this.transform = { scale, ox, oy };
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (w !== this.texW || h !== this.texH) this._allocTargets(w, h);
  }

  _allocTargets(w, h) {
    const gl = this.gl;
    w = Math.max(1, w); // a hidden/zero-size canvas must not create
    h = Math.max(1, h); // zero-size textures (INVALID_VALUE + broken FBOs)
    for (const fb of [this.fbBead, this.fbThrow, this.fbMask]) {
      if (fb) {
        gl.deleteFramebuffer(fb.fb);
        gl.deleteTexture(fb.tex);
      }
    }
    const mk = (tw, th, fmt) => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texStorage2D(gl.TEXTURE_2D, 1, fmt || gl.RGBA16F, tw, th);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const fb = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(
        gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0
      );
      return { fb, tex, w: tw, h: th };
    };
    this.fbBead = mk(w, h);
    this.fbThrow = mk(Math.max(1, w >> 2), Math.max(1, h >> 2));
    this.fbMask = mk(w, h, gl.RGBA8); // full res: crisp cloth outline
    this.texW = w;
    this.texH = h;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  markColors() {
    this.colorsDirty = true;
  }

  /* verts: Float32Array of world XY triangle vertices (3 per triangle) for
   * every panel that currently has cloth; pass null/empty for geometries
   * without structural triangles (mask defaults to full coverage). */
  setTriangles(verts) {
    const gl = this.gl;
    this.haveMask = !!(verts && verts.length);
    if (this.haveMask) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.maskBuf);
      gl.bufferData(gl.ARRAY_BUFFER, verts, gl.DYNAMIC_DRAW);
      this.maskVerts = verts.length / 2;
    }
  }

  render() {
    const gl = this.gl;
    const t = this.transform;
    const p = this.params;
    if (!t || !this.n) return;
    if (this.colorsDirty) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.colors);
      this.colorsDirty = false;
    }
    const inch = this.wpi;
    const sigma = p.sigmaIn * inch;
    const beadGain = p.beadGain;
    const range = p.rangeIn * inch;
    // The throw quad reaches 0.4*ext backwards; keep the isotropic spill
    // (radius spillRangeIn) inside it even when tuned past the throw range.
    const ext = Math.max(range, 2.5 * p.spillRangeIn * inch);
    const setCommon = (prog) => {
      gl.useProgram(prog);
      gl.uniform1f(gl.getUniformLocation(prog, "uScale"), t.scale);
      gl.uniform2f(gl.getUniformLocation(prog, "uOffset"), t.ox, t.oy);
      gl.uniform2f(
        gl.getUniformLocation(prog, "uCanvasPx"), this.texW, this.texH
      );
    };
    gl.disable(gl.DEPTH_TEST);
    gl.bindVertexArray(this.vao);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);

    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbBead.fb);
    gl.viewport(0, 0, this.fbBead.w, this.fbBead.h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    setCommon(this.progBead);
    gl.uniform1f(gl.getUniformLocation(this.progBead, "uRadius"), 4 * sigma);
    gl.uniform1f(gl.getUniformLocation(this.progBead, "uForward"), 0);
    gl.uniform1f(gl.getUniformLocation(this.progBead, "uSigma2"), sigma * sigma);
    gl.uniform1f(gl.getUniformLocation(this.progBead, "uBeadGain"), beadGain);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.n);

    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbThrow.fb);
    gl.viewport(0, 0, this.fbThrow.w, this.fbThrow.h);
    gl.clear(gl.COLOR_BUFFER_BIT);
    setCommon(this.progThrow);
    gl.uniform1f(gl.getUniformLocation(this.progThrow, "uRadius"), 0.75 * ext);
    gl.uniform1f(gl.getUniformLocation(this.progThrow, "uForward"), 0.35 * ext);
    const h = p.standoffIn * inch;
    gl.uniform1f(gl.getUniformLocation(this.progThrow, "uH2"), h * h);
    gl.uniform1f(gl.getUniformLocation(this.progThrow, "uM"), p.lobeM);
    // Gains are specified as intensity at 1" from a bare LED; multiply by
    // inch^2 so the 1/(r^2+h^2) falloff is invariant to world scale.
    gl.uniform1f(
      gl.getUniformLocation(this.progThrow, "uThrowGain"),
      p.throwGain * inch * inch
    );
    gl.uniform1f(
      gl.getUniformLocation(this.progThrow, "uSpillGain"),
      p.spillGain * inch * inch
    );
    gl.uniform1f(gl.getUniformLocation(this.progThrow, "uRange"), range);
    gl.uniform1f(
      gl.getUniformLocation(this.progThrow, "uSpillRange"),
      p.spillRangeIn * inch
    );
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.n);

    gl.bindVertexArray(null);
    gl.disable(gl.BLEND);

    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbMask.fb);
    gl.viewport(0, 0, this.fbMask.w, this.fbMask.h);
    if (this.haveMask) {
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      setCommon(this.progMask);
      gl.bindVertexArray(this.maskVao);
      gl.drawArrays(gl.TRIANGLES, 0, this.maskVerts);
      gl.bindVertexArray(null);
    } else {
      gl.clearColor(1, 1, 1, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.texW, this.texH);
    gl.useProgram(this.progTone);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.fbBead.tex);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.fbThrow.tex);
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, this.fbMask.tex);
    gl.uniform1i(gl.getUniformLocation(this.progTone, "uBead"), 0);
    gl.uniform1i(gl.getUniformLocation(this.progTone, "uThrow"), 1);
    gl.uniform1i(gl.getUniformLocation(this.progTone, "uMask"), 2);
    gl.uniform1f(gl.getUniformLocation(this.progTone, "uExposure"), p.exposure);
    gl.uniform3f(gl.getUniformLocation(this.progTone, "uBg"), ...p.bg);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
