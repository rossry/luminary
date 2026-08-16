# Luminary 2.1

Luminary drives a physical light installation for Next Year on Luna: a
**scaffold** of structural lines carrying individually addressable LEDs,
colored every frame by a **pattern** and streamed over a bit-efficient
**wire protocol** to Adafruit Scorpio controllers — or to a browser, through
the *same* codec, so the demo continuously exercises the production path.

## Install

```bash
git clone https://github.com/rossry/luminary && cd luminary
pip install -r requirements.txt
```

Python ≥ 3.11. That's everything for the server, CLI, and web client.
(Firmware builds need PlatformIO — see `firmware/scorpio/README.md`.)

## Quick start

```bash
# 1. Turn a scaffold into a lights geometry (where each LED is, on which strip)
python -m luminary.cli capture --scaffold examples/hex-demo.scaffold.json \
    -o hex.lights.json

# 2. Render a pattern to a static SVG
python -m luminary.cli render --lights hex.lights.json --pattern spiral \
    -t 2.5 -o hex-spiral.svg

# 3. Watch it live: web server + canvas client at http://localhost:8080
#    (--seed-demo loads the demo geometries so the UI isn't empty)
python -m luminary.cli serve --port 8080 --seed-demo

# 4. Stream to hardware (Scorpio on USB serial)
python -m luminary.cli play --lights hex.lights.json --pattern kaleidoscope \
    --serial /dev/ttyACM0

# 5. No hardware handy? Dry-run the full render+encode pipeline with stats
python -m luminary.cli play --lights hex.lights.json --pattern ripple --duration 5
```

In the web UI, pick a geometry and a pattern and press Play; the header
shows live fps and bytes/light·frame so you can watch the codec work. Add
your own geometries via `POST /api/scaffolds` +
`POST /api/lights/from-scaffold`. To stand up a shared team server (VPS,
Docker, or a container platform), see [`docs/deploy.md`](docs/deploy.md) —
including the security model for the pattern-upload endpoint.

**Where to read more:** the authoritative design is
[`plan/spec/luminary-2.1-spec.md`](plan/spec/luminary-2.1-spec.md)
(paragraph-numbered; `spec §…` references appear throughout the code), and
[`CLAUDE.md`](CLAUDE.md) indexes the documentation for contributors and
agents.

## How it works

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
```

New code also passes `black` and strict `mypy` — see
`plan/guidelines/code-quality.md` and `plan/todo/legacy-mypy-debt.md`.

## Pentagon nets (2.0 heritage)

The pentagon `Net` (Triangles → Facets → Beams) lives on as a *constructor*
(spec §3.8): `luminary.geometry.pentagon.to_scaffold/capture` turn any
`configs/*.json` into scaffold/lights geometries, with beam polygons kept as
per-light display shapes for the renderers. `main.py` retains the 2.0
utilities (`svg`, `validate`, `index`) and its `pattern sample`/`preview`
subcommands now run on the 2.1 engine.

## Contributing

Core development is managed with [Graphite](https://graphite.dev);
contributors can make PRs with whatever git tooling you like. Start with
`CLAUDE.md` for the documentation map and `plan/guidelines/` for workflow.
