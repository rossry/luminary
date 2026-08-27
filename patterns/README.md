# Writing a pattern

Everything you need to contribute a pattern is in this directory and this
file. A pattern is **one Python file** containing a `Pattern` subclass: a
pure, vectorized function from `(lights, t)` to a color per light. The
registry discovers every `*.py` here automatically (names starting with `_`
are skipped) — there is nothing to register, import, or wire up.

```python
import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern

class BreathingRing(Pattern):
    name = "breathing_ring"          # stable slug: CLI / API / dropdown
    description = "A ring of light breathing around the center"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        # Normalize against THIS geometry — never hardcode its size.
        cx = 0.5 * (x.min() + x.max())
        cy = 0.5 * (y.min() + y.max())
        rn = np.hypot(x - cx, y - cy)
        rn = rn / max(1e-6, float(rn.max()))

        ring_center = 0.2 + 0.6 * (0.5 - 0.5 * np.cos(2 * np.pi * t / 9.0))
        glow = np.exp(-((rn - ring_center) ** 2) / (2 * 0.15**2))

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.05 + 0.6 * glow            # L: 0..1
        out[:, 1] = 0.06 + 0.22 * glow           # C: 0..0.4 (hard limit)
        out[:, 2] = (260.0 - 180.0 * glow) % 360 # H: degrees, wraps freely
        return out
```

One `Pattern` subclass per file; `name` must be unique across the
directory. Patterns are looked up by `name` or by file stem.

## What you're given

`lights` is an `(n, 24)` float array — one row per light, columns indexed
by `luminary.geometry.lights.LightColumns` (spec §6.3). The ones that
matter for pattern work:

| Columns | Meaning |
|---|---|
| `X`, `Y` | Position in the piece's plane. **SVG convention: y grows downward** — "up" is negative y. |
| `R`, `THETA` | Polar coordinates about the origin (the pentagon's center hole on the star geometries). |
| `X3`, `Y3`, `Z3` | True 3D position on folded geometries (4A-37 folds onto the physical 3V geodesic sphere: apex +z, the door faces −y, radius ≈ 122 units). All-zero z on flat geometries — gate 3D-only effects on `np.any(lights[:, LightColumns.Z3] != 0)`. |
| `RHO`, `THETA_S`, `PHI_S` | Spherical form of X3/Y3/Z3: radius, azimuth (radians), and polar angle from the apex — `PHI_S` is the "elevation ring" axis. |
| `DX`, `DY` | The beam's throw direction — the fan mesostructure of the physical build. See `prism.py` for what this unlocks. |
| `KIND`, `WEIGHT` | Light kind and interpolation weight. You normally ignore these: render every row and let the engine handle the wire. |

Rows with missing coordinates can be NaN — pass your result through
`luminary.patterns.util.nan_to_black` if your math can propagate them.

**Never assume a geometry.** Your pattern runs on the hex demo (168
lights), the pentagon stars (5,940–6,660 lights), and whatever comes next.
Normalize positions against the bounding box or `max(r)` *inside*
`render()`, as above.

## What you must return

`(n, 3)` float OKLCH, finite everywhere:

- **L** in `[0, 1]`.
- **C** in `[0, 0.4]` — a **hard wire limit** (`C_MAX`, spec §11.4.1).
  Anything above 0.4 is clipped by every consumer; you just lose control
  of your own colors (this bit `firelike.py` once — a constant ~0.05 ΔE
  error on its most saturated lights).
- **H** in degrees; any value is fine, it wraps mod 360.

## The one law: statelessness

Same `(lights, t)` in, same array out, with **no dependence on call
order** (spec §9.1.3). No instance attributes that change, no module
globals that accumulate, no wall-clock, no un-seeded randomness. The
codec recomputes ground truth at arbitrary `t`, decoders resync
mid-stream, and the test suite calls your `render` twice at random times
and asserts bit-identical output (`tests/test_engine_integration.py`).

This costs you nothing once you know the idioms:

- **Per-entity constants** (star positions, phase offsets, lane
  parameters): `luminary.patterns.util.seeded_random(salt, n)` — a
  deterministic uniform array fully determined by the salt string.
- **Discrete events** (bolts, comets, blooms): divide time into fixed
  slots and derive each slot's events from
  `seeded_random(f"myname-{slot}", k)`. Any frame can then reconstruct
  every event that could still be visible by scanning the last few slots.
  Worked examples, simplest first: `plasma_storm.py` (one bolt per slot),
  `emberfall.py` (per-lane spawns), `tidepool.py` (events timed to when a
  moving crest passed each anchor).
- **Whole simulations**, when the thing you want genuinely has state (a
  game, a growth, a collapse): simulate it *once* as a pure function of
  the geometry and an epoch index `floor(t / epoch_len)`, memoize the
  result on a content fingerprint of `lights`, and make `render` a
  lookup into that timeline. Memoization is not state — the cache is
  fully determined by its key, so any call order gives identical
  output. `pacman.py` is the worked example.
- **Envelopes in closed form**: an event at `t0` has intensity
  `attack((t - t0)/rise) * exp(-(t - t0)/decay)` — a pure function of
  `t`, no accumulation.
- **Never visibly repeating**: drive independent motions with
  incommensurate periods (distinct primes, golden-ratio multiples). Two
  sines at 13 s and 29 s realign roughly never.

## The medium (what makes it look good)

This is a physical light sculpture watched at night by dark-adapted eyes,
not a monitor. The craft rules the current set follows:

- **Restraint wins.** Deep, near-black fields with structured light read
  as luminous; full-field brightness reads as a billboard. Keep resting
  L floors around 0.04–0.06 (a few wire quantization steps above zero, so
  darks don't posterize — the wire L step is 1/63).
- **OKLCH is the brush.** Equal L steps look equal; hue walks at constant
  L stay luminous the whole way (`aurora.py` walks green→teal→violet).
  To blend two *color fields* into each other, lerp OKLab vectors
  (`a = C·cos H`, `b = C·sin H`) instead of lerping H — the meeting zone
  desaturates into pearl instead of mudding (`vespers.py`).
- **Size features in facet units.** The piece is built from triangular
  boards subdivided into beam fans; a feature narrower than a facet
  (roughly 1/20 of the piece's span) reads as speckle, not object. Give
  comets, blooms, and ridges gaussian widths of a facet or two.
- **Respect time.** Event attacks ≥ 100 ms, no strobing, and slow is
  usually more beautiful than fast. The geometry is mirror-symmetric
  about x = 0, and its five inner sectors sit at −90° + 36° + k·72° —
  compose with that or deliberately against it (`sanctum.py` locks to it).

## The wire (what makes it cheap)

The engine streams your colors with a dead-reckoning codec (spec §11):
each light coasts on its estimated velocity and only prediction *errors*
cost bytes. Consequences for you:

- Smooth fields with steady motion are nearly free; sparse bright events
  over a calm base are cheap drama. If it looks calm, it streams calm.
- Sudden everywhere-at-once jumps are the expensive case, and per-frame
  slew is capped (~0.24 L / 0.09 C / 89° H per light per frame) — hard
  global flashes will lag a frame or two.
- Measured on the star: the current patterns span 0.27–2.77
  bytes/light·frame uncapped (`plan/spec/implementation-notes.md` §7).
  You don't need to optimize for this, but it's telling that the
  best-looking patterns are also the cheapest.

Keep `render` vectorized (no Python loops over lights; broadcasting over
a few dozen events is fine) and under ~5 ms for ~6,600 lights
(spec §17.3). Fuse exponentials where easy: one `np.exp(a + b)` beats
`np.exp(a) * np.exp(b)` on arrays.

## See it, test it, ship it

```bash
# Watch it live: serve, open the page, pick a geometry + your pattern.
python -m luminary.cli serve --seed-demo          # http://localhost:8080

# Headless still frame, if you're iterating without a browser:
python - <<'EOF'
from luminary.engine.engine import Engine
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture
from luminary.patterns.registry import default_registry
from luminary.render import svg
lights = capture(Net.from_json_file("configs/4A-37.json"))
engine = Engine(lights, default_registry().get("breathing_ring"))
open("/tmp/frame.svg", "w").write(svg.lights_svg(lights, engine.colors_srgb8(t=8.0)))
EOF

# Gates (run before any PR; CI runs the same):
black patterns/your_pattern.py
python -m pytest                 # discovery + statelessness cover you automatically
```

The dev server rescans this directory on restart (or on any
`POST /api/patterns` upload, which hot-reloads the registry). Shared
deployments run with uploads disabled, so contributed patterns ship the
repo way: PR → merge → `git pull` + service restart (`docs/deploy.md`).

## Reading list

Every file here is a worked example. By what it teaches:

| Pattern | Demonstrates |
|---|---|
| `simple.py`, `wave.py`, `breathe.py` | The minimal contract: fields of `(x, y, t)` |
| `spiral.py`, `kaleidoscope.py`, `tunnel_vision.py`, `ripple.py` | Polar composition around the center |
| `firelike.py` | Per-light hashed noise (and the C ≤ 0.4 cautionary tale) |
| `plasma_storm.py` | Slot-hashed events: deterministic lightning |
| `aurora.py` | Layered drifting ridges; hue ramps walked in OKLCH; hashed star twinkle |
| `emberfall.py` | Events on polar lanes; facet-scale widths; fused-exponential comet math |
| `sanctum.py` | Phase-locking to the piece's own five-fold structure |
| `prism.py` | The `DX`/`DY` beam-direction columns — patterns impossible on a pixel grid |
| `tidepool.py` | Closed-form event timing (flares scheduled by a moving crest) |
| `vespers.py` | OKLab-vector color blending; multi-minute incommensurate orbits |
| `pacman.py` | A precomputed simulation played back statelessly; per-epoch rounds; a graph recovered from the lights themselves, cached by content fingerprint |
| `serpent.py` | Multiple agents co-simulated on one event timeline; a body as a sliding arclength window over a per-round `(row, s)` table |
| `life.py` | A CA rule chosen by measurement, not assumption; births and deaths as directional sweeps; hue as ancestry |

`legacy/` holds pre-2.1 stateful patterns that don't meet this contract;
`plasma_storm.py` is the worked example of converting one.
