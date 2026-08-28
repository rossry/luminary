# Writing a pattern

Everything you need to contribute a pattern is in this directory and this
file. A pattern is **one Python file** containing a `Pattern` subclass: a
pure, vectorized function from `(lights, t)` to a color per light. The
registry discovers every `*.py` here automatically and recursively —
volume subdirectories included; path components starting with `_` and the
`legacy/` tree are skipped — there is nothing to register, import, or
wire up.

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

The directory is organized into volumes:

| Where | What |
|---|---|
| `*.py` (top level) | The ported 2.0 set and small worked examples |
| `book-one/` | The 2026-07 look-dev set — one axis of the medium each |
| `conifer/` | conifer egitto's set (`life`, `pacman`, `serpent`) |
| `book-two/` | Patterns and shows **composed from the shared library** (below) |
| `legacy/` | Pre-contract patterns; not loaded |

New standalone patterns are welcome anywhere sensible; new *composed*
work belongs in `book-two/`.

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
| `DX`, `DY` | The beam's throw direction — the fan mesostructure of the physical build. See `book-one/prism.py` for what this unlocks. |
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
  `book-one/emberfall.py` (per-lane spawns), `book-one/tidepool.py` (events timed to when a
  moving crest passed each anchor).
- **Whole simulations**, when the thing you want genuinely has state (a
  game, a growth, a collapse): simulate it *once* as a pure function of
  the geometry and an epoch index `floor(t / epoch_len)`, memoize the
  result on a content fingerprint of `lights`, and make `render` a
  lookup into that timeline. Memoization is not state — the cache is
  fully determined by its key, so any call order gives identical
  output. `conifer/pacman.py` is the worked example.
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
  L stay luminous the whole way (`book-one/aurora.py` walks green→teal→violet).
  To blend two *color fields* into each other, lerp OKLab vectors
  (`a = C·cos H`, `b = C·sin H`) instead of lerping H — the meeting zone
  desaturates into pearl instead of mudding (`book-one/vespers.py`).
- **Size features in facet units.** The piece is built from triangular
  boards subdivided into beam fans; a feature narrower than a facet
  (roughly 1/20 of the piece's span) reads as speckle, not object. Give
  comets, blooms, and ridges gaussian widths of a facet or two.
- **Respect time.** Event attacks ≥ 100 ms, no strobing, and slow is
  usually more beautiful than fast. The geometry is mirror-symmetric
  about x = 0, and its five inner sectors sit at −90° + 36° + k·72° —
  compose with that or deliberately against it (`book-one/sanctum.py` locks to it).
- **Slow means large.** A slow action must be correspondingly big: an
  event that takes 40 seconds should be sphere-wide (a tide crossing
  the whole layout, a population filling a sky), never a small thing
  moving slowly. And every scene should be *going* somewhere, *coming*
  from somewhere, or *arrived* somewhere — and know which. The library
  arcs (`fill_from/to`, `gain_from/to`, `crest_at`, all over `arc_s`)
  exist so a movement's parameters travel its whole duration;
  `nocturne`'s seven movements are the worked example, one dramaturgy
  each.
- **No long flat scene.** Set `arc_s` to the movement's own duration —
  that is what it is for, and a movement whose parameters do not travel
  is a still image held for as long as the track lasts. Past roughly
  six or seven minutes one arc stops being enough, because a single
  monotone ramp over a quarter of an hour reads as flat too; there, nest
  a `Conductor` *inside* the movement and give the stretch two or three
  scenes. That keeps the outer cue sheet — the track boundaries — exactly
  where the record put it, while the inside gets a shape. `koln`'s
  sixteen-minute "revisited" (settling / the long climb / coming to rest)
  and `apollo`'s "An Ending (Ascent)" (both words of the title, in order)
  are the worked examples.
- **Duty cycle.** A fully-colored field targets a *mean* around
  0.1–0.3 L; the field's own texture tops out near ~0.3–0.4. Small
  figures — stars, ring crests, candle cores — sit above the field
  lane (0.5–0.8), and only point/streak events (meteors, lightning)
  may burst toward full brightness. If you are using blank space,
  decide deliberately which lane your bright things live in.
  `tests/test_compose.py::test_duty_cycle_no_movement_black_or_blasting`
  holds every conducted movement to "never effectively black, never a
  full-field blast".

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
luminary serve --seed-demo          # http://localhost:8080

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

## Composing from the library (book two)

`luminary/patterns/` is the importable library — write field math once
there, publish tuned voices here (invariant §2.9: the mapping visuals and
show patterns share these exact implementations):

- **`palettes`** — `Palette` (OKLCH stops sampled by any scalar field),
  `blend_oklch` (THE perceptual crossfade: hue the short way, chroma
  through neutral), and tuned house palettes (`NIGHT_SKY`, `CANDLE`,
  `AURORA`, `EMBER`, `SEA_GLASS`).
- **`easing`** — `smoothstep`, `smootherstep`, `breath`, `env_ad`,
  `wrap01`: nothing in a good pattern moves linearly.
- **`fields`** — deterministic value noise / `fbm` / domain `warp`
  (integer-hash based, identical on every platform) and `ring_field`,
  the shared descending-ring motif.
- **`primitives`** — `Starfield`, `NoiseGlow`, `AuroraVeils`, `RingWave`:
  complete patterns whose knobs are **class attributes**. Publishing a
  tuned voice is a subclass that overrides values; typos in overrides
  fail loudly:

  ```python
  from luminary.patterns.primitives import NoiseGlow

  class Weather(NoiseGlow):          # patterns/book-two/weather.py
      name = "weather"
      description = "Sea-glass weather: warped noise banks drifting slowly"
      scale = 2.4
      speed = 0.022
  ```

- **`compose`** — `Movement` + `Conductor`: a show is itself a Pattern.
  Sequence primitive instances with durations and fade-in windows; the
  conductor maps global `t` onto one movement (two during a crossfade,
  never more), blends with `blend_oklch`, and stays a pure function of
  `(lights, t)` — seekable, stateless, gapless. A non-looping conductor
  exposes `duration`, which the stage queue uses to advance shows
  without gaps.

  ```python
  from luminary.patterns.compose import Conductor, Movement
  from luminary.patterns.palettes import CANDLE, EMBER
  from luminary.patterns.primitives import NoiseGlow, Starfield

  class Vigil(Conductor):            # patterns/book-two/vigil.py
      name = "vigil"
      description = "Embers, then stars"

      def __init__(self) -> None:
          super().__init__([
              Movement(NoiseGlow(palette=EMBER, speed=0.02), 480.0, fade=12.0),
              Movement(Starfield(density=0.03), 420.0, fade=35.0),
          ])
  ```

  `nocturne.py` is the worked example: an hour in seven movements,
  neighboring movements keyed to neighboring hue families so every
  crossfade blends kin colors. Composition overhead is O(1) per frame
  (a searchsorted plus at most one blend), so conducted shows cost what
  their movements cost. Conductors nest — a show is a Pattern, so it
  can be a movement of a larger show (`overnight.py` opens with the
  whole of Nocturne as its first chapter).

- **`repertoire`** — the importable home of the substantial book-two
  voices (`SmallPlanet`, `Fireflies`, `Relay`) and show builders
  (`nocturne_movements`). Pattern files are exec-loaded and can never
  be imported, so the rule is: **art lives in the library exactly when
  something else composes it**; the file here stays a thin
  registration subclass either way.

## Reading list

Every file here is a worked example. By what it teaches:

| Pattern | Demonstrates |
|---|---|
| `simple.py`, `wave.py`, `breathe.py` | The minimal contract: fields of `(x, y, t)` |
| `spiral.py`, `kaleidoscope.py`, `tunnel_vision.py`, `ripple.py` | Polar composition around the center |
| `firelike.py` | Per-light hashed noise (and the C ≤ 0.4 cautionary tale) |
| `plasma_storm.py` | Slot-hashed events: deterministic lightning |
| `book-one/aurora.py` | Layered drifting ridges; hue ramps walked in OKLCH; hashed star twinkle |
| `book-one/emberfall.py` | Events on polar lanes; facet-scale widths; fused-exponential comet math |
| `book-one/sanctum.py` | Phase-locking to the piece's own five-fold structure |
| `book-one/prism.py` | The `DX`/`DY` beam-direction columns — patterns impossible on a pixel grid |
| `book-one/tidepool.py` | Closed-form event timing (flares scheduled by a moving crest) |
| `book-one/vespers.py` | OKLab-vector color blending; multi-minute incommensurate orbits |
| `conifer/pacman.py` | A precomputed simulation played back statelessly; per-epoch rounds; a graph recovered from the lights themselves, cached by content fingerprint |
| `conifer/serpent.py` | Multiple agents co-simulated on one event timeline; a body as a sliding arclength window over a per-round `(row, s)` table |
| `conifer/life.py` | A CA rule chosen by measurement, not assumption; births and deaths as directional sweeps; hue as ancestry |
| `book-two/starlight.py`, `weather.py`, `veils.py`, `ringfall.py` | The registration idiom: a tuned voice as class-attribute overrides of a shared primitive |
| `book-two/nocturne.py` | A conducted night: movements timed to their own tracks (`Movement(..., audio=…)` — queued as chapters, the music changes with the act), crossfade windows, palette continuity |
| `small_planet` (voice in `repertoire`) | Spatial composition: layers lerped in OKLab vec space (one conversion for six blends); seam-free sphere noise; a sub-primitive blended in by mask; geometry statics memoized on a content fingerprint |
| `fireflies` (voice in `repertoire`) | Emergent behavior in closed form: slot-hashed events whose offsets lerp toward a metronome by a coherence curve — synchrony without simulation; agent-to-light gaussian pools via one matmul |
| `book-two/apollo.py` | The cue-sheet show idiom: an album as a Movement list whose durations are the track lengths, crossfades as the drift tolerance — pair with the record on the stage. Every track's `arc_s` is its own length, so no scene ends where it began; tracks 1, 6 and 12 share a `salt`, so the record literally closes under the sky it opened under |
| `relay` (voice in `repertoire`) | The wiring as the medium: `CONTROLLER`/`CHANNEL`/`INDEX` make every strip a lane, and races run the serpentine in index order; per-lane state gathered to lights by `np.unique` inverse |
| `embers` (voice in `primitives`) | Coupled figures: one wind field dims the cloud, scars it (closed-form geometric heal — damage outlives the gust), gates the coals into the banks, and times each coal's own flare tail, so a coal's brightest seconds are its last — physics as dramaturgy |
| `starfall` (voice in `primitives`) | Departure as narrative: a hash rank maps through schedule nodes to each star's departure time — one single swell, densest just before the last star falls onto a drained-black sky — and the streak is a pure function of (t − departure); the schedule IS the story |
| `book-two/promises.py` | A persistent motif under a whole show: every movement is `Layered(scene, THE SAME Motif)` — the temporal analogue of small_planet's spatial masks. The scenes around it are three crests that arrive earlier and burn hotter in turn (`crest_at` 0.62 → 0.50 → 0.42): a shape spread across movements, not inside one |
| `book-two/spiegel.py` | Symmetry as the subject: every element lives on or mirrors across the geometry's own x = 0 plane, held by a mirror-pair test. And development without dynamics — the phrases widen and lengthen (a precomputed boundary array, `searchsorted`, still pure) while nothing gets brighter: the reach is the whole arc |
| `book-two/koln.py` | Declared audio: `Pattern.audio` names the soundtrack, the stage pre-selects and auto-attaches it when the file is present, and the track's exact length times the entry. Also nesting for length: each part over six minutes is a sub-`Conductor`, and `RingWave(meander=…)` colors each ring by when it launched, so fifteen minutes of unbroken pulse is also one continuous walk through gold |
| `book-two/overnight.py` | Nested conductors: a looping dusk-to-dawn program whose first chapter is the whole of Nocturne, by import — one name to queue when the sun goes down |

`legacy/` holds pre-2.1 stateful patterns that don't meet this contract;
`plasma_storm.py` is the worked example of converting one.
