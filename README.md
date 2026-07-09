# Luminary 2.1

A project for Next Year on Luna 2025. Luminary drives a physical light
installation: a **scaffold** of structural lines carrying individually
addressable LEDs, colored every frame by a **pattern** and streamed over a
bit-efficient **wire protocol** to Adafruit Scorpio controllers — or to a
browser, through the *same* codec, so the demo continuously exercises the
production path.

The authoritative design is **`plan/spec/luminary-2.1-spec.md`** (paragraph-
numbered; §-references appear throughout the code). Core development is
managed with [Graphite](https://graphite.dev); contributors can use plain git.

## Architecture in one paragraph

A **lights geometry** (`*.lights.json`, spec §6) is the canonical per-light
table: identity `{controller, channel, index}`, kind (active / interpolated /
inactive), coordinates in four spaces, direction+extent, and normal — loaded
into one NumPy array. **Patterns** (spec §9) are pure vectorized functions
`render(lights, t) -> OKLCH`. The **engine** (spec §10) renders and encodes
each frame with the **codec** (spec §11): 6/5/8-bit quantized OKLCH,
2-byte-per-light keyframes, dead-reckoning deltas ranked by error under a
byte budget. **Drivers** (spec §12) move those bytes over serial or
WebSocket; the **Scorpio firmware** (spec §13, `firmware/`) and the **web
client** (spec §14) decode with bit-identical integer predictors, verified
against shared golden vectors (`firmware/golden/`).

## Quickstart

```bash
pip install -r requirements.txt

# Produce a lights geometry from a scaffold (spec §7.2)
python -m luminary.cli capture --scaffold examples/hex-demo.scaffold.json \
    -o hex.lights.json

# Static render of a pattern at t=2.5s
python -m luminary.cli render --lights hex.lights.json --pattern spiral \
    -t 2.5 -o hex-spiral.svg

# Web server + live canvas client (http://localhost:8080)
python -m luminary.cli serve --port 8080

# Stream to hardware
python -m luminary.cli play --lights hex.lights.json --pattern kaleidoscope \
    --serial /dev/ttyACM0

# Codec dry-run with stats (no output device needed)
python -m luminary.cli play --lights hex.lights.json --pattern ripple \
    --duration 5
```

The web UI (`serve`) lists stored geometries and patterns, plays any pattern
over the real wire protocol, and shows live bytes/light·frame so you can see
the dead-reckoning codec work.

## Web API (spec §15)

| Endpoint | Purpose |
|---|---|
| `POST /api/scaffolds` / `GET /api/scaffolds[/{id}[/view]]` | save / list / fetch / render scaffolds |
| `POST /api/lights` / `GET /api/lights[/{id}[/view|/layout]]` | save / list / fetch / render lights; client draw layout |
| `POST /api/lights/from-scaffold` | capture with defaults: `{scaffold_id, params}` |
| `GET/POST /api/patterns` | list / upload+hot-reload patterns |
| `WS /api/play?lights=ID&pattern=NAME` | wire-protocol streaming |

## Pattern development

Create a file in `patterns/`:

```python
import numpy as np
from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern

class MyPattern(Pattern):
    name = "my_pattern"
    description = "What it looks like"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.6                                  # L: 0..1
        out[:, 1] = 0.3                                  # C: 0..0.4
        out[:, 2] = (x + y + t * 60.0) % 360.0           # H: degrees
        return out
```

Rules (spec §9.1): vectorized NumPy only, and **stateless** — output depends
only on `(lights, t)`; use `luminary.patterns.util.seeded_random` for
per-entity constants. Upload via `POST /api/patterns` or drop the file in
`patterns/` — the registry hot-reloads. Stateful 2.0 patterns that predate
this contract are parked in `patterns/legacy/`.

## Firmware

`firmware/scorpio/` is a PlatformIO/Arduino project for the Feather RP2040
SCORPIO (spec §13): serial wire in, eight NeoPXL8 strips out, with fixed-point
OKLCH→RGB and on-device interpolation of non-transmitted lights. Its decoder
core is plain C++ and host-tested against the golden vectors:

```bash
cd firmware/test/host && make run
node tests/js/test_decoder.mjs        # same vectors, browser decoder
```

## Tests

```bash
python -m pytest            # includes golden-vector + JS + C++ conformance
python -m mypy luminary/... --explicit-package-bases
```

## Pentagon nets (2.0 heritage)

The pentagon `Net` (Triangles → Facets → Beams) lives on as a *constructor*
(spec §3.8): `luminary.geometry.pentagon.to_scaffold/capture` turn any
`configs/*.json` into scaffold/lights geometries, with beam polygons kept as
per-light display shapes for the renderers. `main.py` retains the 2.0
utilities (`svg`, `validate`, `index`) and its `pattern sample`/`preview`
subcommands now run on the 2.1 engine.
