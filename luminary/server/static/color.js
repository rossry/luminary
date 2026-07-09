/* OKLCH -> sRGB8, the spec §8.4 math (JavaScript mirror of color/convert.py).
 * Like the firmware, the client clamps out-of-gamut channels (spec §13.4);
 * the chroma-reducing gamut clip is an authoring-path nicety.
 */

export function oklchToSrgb8(L, C, Hdeg) {
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
  return [gamma8(r), gamma8(g), gamma8(bb)];
}

function gamma8(c) {
  c = c < 0 ? 0 : c > 1 ? 1 : c;
  const s = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  return Math.round(255 * (s < 0 ? 0 : s > 1 ? 1 : s));
}
