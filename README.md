# Luminary 2.1

*In a hurry? [`QUICKSTART.md`](QUICKSTART.md) gets patterns playing in
three commands.*

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

Running an actual installation is a different path — find and register the
boards, flash them, map them, then stream to all of them with a live preview:

```bash
python -m luminary.cli boards                     # verify + register what's on USB
python -m luminary.cli flash --max-per-strip 180  # build, flash, prove it came back
python -m luminary.cli map                        # interactive deployment mapping
python -m luminary.cli show --lights pentagon-4A-33 --pattern aurora
```

`show` streams to the boards and mirrors the same wire bytes to
`/preview` — one engine, so the preview is evidence of what the hardware
received rather than a second render. Step-by-step:
[`QUICKSTART.md`](QUICKSTART.md).

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
| `GET /demo/mapping` | the scrambled-build mapping tutorial, mounted here by `serve` (opt out: `--no-mapping-demo`); also standalone via `python -m luminary.mapping.web` |
| `GET …/api/mapping/layout` · `WS …/api/mapping/{window,wire,control}` | the mapping app's own API (`luminary.mapping.web`, under whatever prefix it serves at): layout+plan+state JSON; wire-codec streams; key events. A live session's window page is `/window` — its own process, `python -m luminary.cli map --web` |
| `GET /stage` · `GET/POST /api/queue` · `DELETE /api/queue/{i}` · `POST /api/queue/{play_next,move,skip,clear}` | the stage: viewer/control page and the play-queue API (tracklist + repeats cycle + now-playing; mounted by `serve`, opt out: `--no-stage`). Mutations take the stage key when one is configured (below) |
| `POST /api/repeats/move` · `DELETE /api/repeats/{i}` | reorder / cancel turns of the stage's repeats cycle |
| `WS /api/stage` · `GET /api/stage/{layout,patterns,chapters?pattern=N}` | the stage's wire-codec stream (SESSION on join, `{"type":"resync"}` back), its canvas draw layout, panel pattern metadata (notes, `loop`, `has_chapters`), and one pattern's chapter tree (`[]` if chapterless) |
| `GET /api/audio` | audio inventory (`var/audio/`): `[{name, seconds}]`, `seconds` null when unreadable |

## The stage (play queue)

`serve` runs the **stage** at `/stage`: one engine over the production
sphere geometry (`--stage-lights` overrides with a store id or lights
file) playing a persisted tracklist, gaplessly — entries advance by
pattern swap on the same engine, each pattern seeing t from its own
entry's start, so long-form shows and audio cue sheets align at 0. An
entry is `{pattern, duration, audio, repeat}`: `audio` names a file in
`var/audio/`, played by an auto-detected local player
(`mpv`/`cvlc`/`ffplay`; `--audio-player CMD` overrides) started at the
entry's t=0. **The track times the entry**: with audio attached,
`duration` null means the file's exact length, a longer ask is trimmed
to it at add time, and a shorter ask cuts the entry there with a short
audio fade-out (mpv/ffplay; others cut hard). Without audio, `duration`
null defers to the pattern's own `duration` attribute (else it plays
until skipped). A pattern may declare its soundtrack (`Pattern.audio`,
a bare filename; a composition's movements may each declare their own
via `Movement(..., audio=…)`): left unspecified, an entry picks up the
declared file when it is present — and a composition queued with audio
unspecified starts each chapter's own declared track at that chapter.
The page pre-selects the declaration (`♪ per chapter` for chaptered
shows) and marks declared-but-missing files (`wants ♪ name`).
"Play next" (`/api/queue/play_next`) inserts right after
the playing entry. An exhausted queue takes the next turn of the
repeats cycle (below); with that empty too it holds the last pattern,
looping — the sphere never goes dark — and both lists survive restarts
(`var/stage/queue.json`). The page is a thin adapter over
`/api/queue`; every playback decision lives server-side in
`luminary/stage/core.py`.

**Chapters.** A queued composition (a `Conductor` — anything answering
`chapters()`) expands, the moment it reaches the head of the queue,
into one entry per top-level chapter, titled `composition/chapter`;
a nested composition expands one level again when *it* reaches the
head (`comp/chapter/subchapter`), so the queue always shows the
current show at chapter granularity while later chapters stay one
level deep. Chapter entries keep the top-level pattern with an offset
into its own timeline, so adjacent chapters advance **seamlessly** —
no keyframe, timeline continuous, the composition's own crossfades
and audio intact — and *skip means next chapter*. A skip is a jump,
so it re-keyframes. Queued (not yet expanded) compositions are
click-to-preview expanders in the page, showing the server-computed
chapter tree; the viewer header shows the playing chapter's path with
its liner `notes` (from `Movement`/`Pattern.notes`) beneath in
italics. An instance of a `loop=True` composition gets one full pass
(`pattern.total`) as its duration.

**Repeats.** The stage keeps a second list: a round-robin cycle of
`{pattern, title, audio}` tokens with its own pane and controls.
Adding with the `repeat` box checked (its default is the pattern's own
`loop` flag) queues one instance *and* one token; whenever the
play-through queue runs out, the head token spawns a fresh instance
(expanding into chapters at the head as usual) and moves to the back
of the cycle — an overnight program repeats forever until its token is
cancelled. "Clear queue" drops only the play-through list; the cycle
keeps going until its tokens are removed.

**Production posture.** Configure a stage key (`serve --stage-key K`,
or env `LUMINARY_STAGE_KEY`; the flag wins) and every mutating
endpoint (add, play-next, remove, move, skip, clear, repeats CRUD)
requires it in an `X-Stage-Key` header — wrong or missing gets a 403
with a JSON error the page surfaces. Read-only traffic (the page, the
WS stream, queue/layout/patterns/chapters/audio GETs) is never gated,
so anyone can watch. Put the key in the systemd unit's environment
(`Environment=LUMINARY_STAGE_KEY=…`) and share the control URL only
with VJs — the page takes the key from its footer field (persisted in
localStorage) or once via a `#key=…` URL fragment. With no key
configured, endpoints stay open (LAN deployments).

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
per-entity constants. Files in `patterns/` are discovered on server start
(recursively — the directory is organized into volumes: `book-one/`,
`conifer/`, `book-two/`) and on any `POST /api/patterns` upload, which
hot-reloads the registry.

For composed work there is a shared library in `luminary/patterns/`:
palettes with perceptual OKLab blending, easing, deterministic noise
fields, parametrized primitives (`Starfield`, `NoiseGlow`, `AuroraVeils`,
`RingWave`), and `Movement`/`Conductor` for sequencing whole shows as
stateless patterns with crossfades (`patterns/book-two/nocturne.py` is a
conducted hour). See the "Composing from the library" section of the
contributor guide.

**The full contributor guide is [`patterns/README.md`](patterns/README.md)**:
the contract, the lights-array columns, statelessness idioms for events and
randomness, craft notes for the physical medium (gamut, scale, motion, wire
cost), the iterate/test loop, and a reading list mapping every shipped
pattern to the technique it demonstrates. If you have an idea for a pattern,
that page is everything you need. Stateful 2.0 patterns that predate the
contract are parked in `patterns/legacy/`.

## Firmware

`firmware/scorpio/` is a PlatformIO/Arduino project for the Feather RP2040
SCORPIO (spec §13): serial wire in, eight NeoPXL8 strips out, with fixed-point
OKLCH→RGB and on-device interpolation of non-transmitted lights. Its decoder
core is plain C++ and host-tested against the golden vectors:

```bash
cd firmware/test/host && make run
node tests/js/test_decoder.mjs        # same vectors, browser decoder
```

Flashing is `python -m luminary.cli flash` (PlatformIO underneath, one
build per controller id, verified with an identity probe afterwards). A
board that has never been flashed does not enumerate at all: hold BOOTSEL
while plugging it in, and `luminary boards` will report it as `bootsel`.

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
