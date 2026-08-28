# Luminary 2.1 — Implementation Notes

> Companion to `luminary-2.1-spec.md` (the authoritative *design*). This file
> records how that design is *realized in this repository* — the component
> map, the invariants you must not break, the cross-language conformance
> workflow, verified performance numbers, and what is deliberately deferred.
> Read this before modifying the engine, codec, or geometry model.

## 1. Component map (module → spec section)

| Module | Spec | Role |
|---|---|---|
| `luminary/geometry/coords.py` | §4 | Vectorized conversions between the four coordinate spaces; the single `derive_all` rule every loader uses |
| `luminary/geometry/scaffold.py` | §5 | Scaffold lines: endpoints, optional bend midpoint, three per-side in-surface normals (default = +90° CCW of the chord) |
| `luminary/geometry/lights.py` | §6 | **The canonical representation**: `LightColumns` (24-column NumPy array), kinds, arc-length interpolation weights, canonical `(controller, channel, index)` sort, JSON round-trip, per-channel strip maps |
| `luminary/geometry/capture/from_scaffold.py` | §7.2 | The default capture (exit condition): spacing/count, channel maps, 1-in-k interpolation policy, throw extents |
| `luminary/geometry/capture/from_scan.py` | §7.4 | Camera-scan capture — **interface-only stub**; raises `NotImplementedError` |
| `luminary/geometry/pentagon/` | §5.5, §7.3 | 2.0 `Net` → scaffold/lights adapters; beam polygons become per-light `display` shapes; fills X3/Y3/Z3 by barycentric fold when the config carries `points3d` |
| `configs/sphere3v.py` | §4.1 | The canonical 3V geodesic sphere of the physical build (first-principles trisect-and-project; vertex ids per the construction app). Carries the plan-A panel faces and the electronics plan (7 data units, base station) |
| `luminary/color/convert.py` | §8 | Vectorized OKLCH/OKLab/sRGB hot path; normative §8.4 matrices; chroma-reducing gamut clip |
| `luminary/color/color.py` | §8.5 | Scalar `Color` for config parsing **only** — never per-frame |
| `luminary/patterns/base.py` | §9.1 | `Pattern.render(lights, t: float) -> (n,3) OKLCH`, pure and vectorized |
| `luminary/patterns/registry.py` | §9.3 | Discovery + hot reload with error isolation; compiles source directly (see §5 below) |
| `luminary/patterns/util.py` | §9.4 | Column accessors, `seeded_random` for deterministic per-entity constants, `phi_theta` (spherical coords with a planar fallback on unfolded nets) |
| `luminary/patterns/palettes.py` | §9.4 | `Palette` (OKLCH stops sampled by scalar fields) and `blend_oklch` — THE perceptual crossfade (OKLab vector plane); house palettes |
| `luminary/patterns/easing.py` | §9.4 | `smoothstep`/`smootherstep`/`breath`/`env_ad`/`wrap01` — closed-form temporal shaping |
| `luminary/patterns/fields.py` | §9.4 | Deterministic uint64-hash value noise, `fbm`, domain `warp`; `ring_field`, the shared descending-ring motif (single source for mapping visuals *and* show patterns, §2.9) |
| `luminary/patterns/primitives.py` | §9.4 | `Primitive` (class-attribute parameter schema, validated overrides) + `Starfield`/`NoiseGlow`/`AuroraVeils`/`RingWave` — the shared parametrized voices |
| `luminary/patterns/compose.py` | §9.1, §9.4 | `Movement` + `Conductor`: shows as stateless Patterns; searchsorted slot lookup, ≤2 child renders/frame, OKLab crossfades, `duration` as the queue-advance signal |
| `luminary/comms/protocol.py` | §11.4, §11.7 | Wire constants: COBS+CRC16 framing, 13-byte header (f64 `t`), quantization, keyframe/delta word packing, varints, SESSION payloads |
| `luminary/comms/predictor.py` | §11.5 | The normative integer dead-reckoning step — shared by encoder mirror and decoder so they cannot diverge |
| `luminary/comms/codec.py` | §11.6–§11.8 | `Encoder` (error-ranked budgeted deltas, keyframe cadence, per-controller frames) and the reference `Decoder` |
| `luminary/engine/engine.py` | §10 | `lights + pattern + t → wire frames`; the single pipeline assembly point; `colors_srgb8` for static renders |
| `luminary/drivers/serial_driver.py` | §12.2 | One process, one engine, port-per-controller; baud-derived budgets; HELLO/RESYNC |
| `luminary/drivers/websocket_driver.py` | §12.3 | Same bytes over WS; JSON control inbound (resync / set_pattern / pause / resume) |
| `luminary/mapping/store.py` | `plan/mapping/DESCRIPTION.md` "Saved state" | One YAML per board (`mapping-<controller_id>.yaml`, schema `luminary.mapping/1`): write→fsync→readback→`.bak` discipline, `--continue` progress markers (dropped when a board completes), dated backups, and `--trust-boards` over the `BoardStore` protocol (`SerialBoards` raises toward the board-storage firmware handoff) |
| `luminary/mapping/serial_sink.py` | `plan/mapping/DESCRIPTION.md` | RESYNC identity probe (port ↔ compiled-in controller id, as `firmware/tools/whoami.py`) and the wire-frame sink routing frames by header controller byte; degrades to window-only with no pyserial/ports |
| `luminary/mapping/tui.py` | `plan/mapping/DESCRIPTION.md` "Surface-agnostic core" | Terminal adapter: cbreak arrows/WASD/enter → Events, one status line, monotonic tick loop, save + SESSION refresh on every state change |
| `luminary/render/projection.py` | §14.4 | Shared world→2D layout for SVG **and** canvas (one projection rule) |
| `luminary/render/svg.py` | §14.5 | Static SVG of scaffolds / lights (rendered once, never per frame) |
| `luminary/server/app.py`, `store.py` | §15 | FastAPI adapter (all exit-condition endpoints) over a content-addressed file store |
| `luminary/server/static/decoder.js`, `color.js`, `client.js`, `glow.js` | §14.2–§14.3 | Browser decoder (conformance sibling), color math, canvas client, WebGL2 realistic cloth render (§14.3.3) |
| `luminary/cli.py` | §16 | `serve` / `play` / `capture` / `render` / `map` — every verb an adapter over the one engine |
| `firmware/scorpio/lib/lumicodec/` | §13 | Plain-C++17 decoder core + Q14 fixed-point color; host-compilable, no Arduino deps |
| `firmware/scorpio/src/main.cpp` | §13 | Arduino sketch: serial in → NeoPXL8 out (not compilable without the Arduino toolchain) |
| `firmware/golden/case1/` | §11.9 | Checked-in conformance corpus (see §3 below) |
| `scripts/generate_golden.py` | §11.9 | Deterministic golden-vector generator |
| `main.py` | — | 2.0 entry point; `svg`/`validate`/`index` unchanged; `pattern sample`/`preview` now delegate to the 2.1 engine |

## 2. Invariants — do not break these

1. **One engine, wire bytes out** (spec §1.3.1, §2.1.2). Every consumer —
   serial, WebSocket, tests — gets frames from `Engine.frame(t)`. Never add a
   second place that renders a pattern and encodes it.
2. **Stateless patterns** (spec §1.3.4, §9.1.3). `render(lights, t)` must be
   a pure function; the codec recomputes ground truth per frame and keyframes
   must be deterministic. `tests/test_engine_integration.py::
   test_statelessness_all_patterns` enforces this for every discovered
   pattern.
3. **Canonical row order** (spec §6.4). The lights array is sorted by
   `(controller, channel, index)`; the codec's active-slot numbering, the
   SESSION strip maps, and all three decoders depend on it.
4. **Encoder mirrors decoder through shared code** (spec §11.5.3). The
   encoder updates its model by calling the *same* `predictor.apply_delta` /
   `apply_keyframe` used by the reference decoder. If you change predictor
   arithmetic, you have changed the wire protocol — see §3.
5. **Integer predictor arithmetic is normative** (spec §11.5.4): int32,
   arithmetic (floor) shifts, always-positive mod-256 hue. Python (NumPy),
   JavaScript (`|0`, `&255`), and C++ (`int32_t`) implement it bit-for-bit.
6. **Budget caps DELTA frames only**; KEYFRAMEs are exempt and amortized by
   `keyframe_interval` (see `CodecConfig` docstring). Link budgeting leaves
   headroom for them (`serial_driver.budget_for_baud` uses 0.8 utilization).
7. **Scalar `Color` never appears on the per-frame path** (spec §8.5.1); the
   hot path is `color/convert.py` array functions only.
8. **No per-light Python loops on the hot path** (spec §1.3.3). Per-light
   loops are tolerated only in load/capture-time code.
9. **One logic path across modes — surfaces are thin adapters.** Demo,
   tutorial, TUI, web, and production must run the *same* state,
   persistence, field-evaluation, and decision code; a surface may only
   adapt I/O (keys → events, frames → paint, placement of its lights).
   Any logic that exists once per surface is a production-divergence
   bug even when its output looks right — twice this shipped and broke
   in the field (wire-side field evaluation; a memory-only demo store).
   Concretely: mapping visual fields render net-side and are gathered
   by `ref`; the per-light role rule is `SessionCore._strip_roles`,
   called by both builders; SESSION resync is core-owned
   (`resync_sinks`); all mapping state persists through `MappingStore`
   (the demo included); the mockup paints through server-computed
   `strip_refs`; runtime-state paths resolve through
   `luminary/statedir.py`; shared visual motifs live once in the
   pattern library (`ring_field` in `luminary/patterns/fields.py`
   serves both the mapping stage-C ring/finale waves and show
   patterns; crossfading is `palettes.blend_oklch` wherever two color
   fields meet). Where an adapter *must* carry a parallel
   table (the web/TUI key maps), a conformance test holds it to one
   canon (`tests/test_mapping_keys.py`) — the golden-vector philosophy.
   When adding a surface or a feature, ask: "where does this logic
   already live?" — never re-derive it locally.

## 3. Changing the wire protocol — the conformance workflow

There are **three decoder implementations** of one spec (spec §1.3.7):
Python (`luminary/comms/codec.py` — the reference), JavaScript
(`luminary/server/static/decoder.js`), C++
(`firmware/scorpio/lib/lumicodec/`). They are held together by the golden
vectors in `firmware/golden/case1/`.

Any change to framing, quantization, word formats, SESSION layout, or
predictor arithmetic requires, in order:

1. Update `plan/spec/luminary-2.1-spec.md` (§11) — the spec is authoritative.
2. Update `protocol.py`/`predictor.py`/`codec.py` (reference).
3. Update `decoder.js` and `lumicodec.{h,cpp}` to match.
4. Regenerate vectors: `python scripts/generate_golden.py` (deterministic —
   reruns must be byte-identical; `tests/test_golden.py` checks this).
5. Run the full conformance set: `python -m pytest tests/test_golden.py`
   (this builds and runs the C++ host test with g++ and the JS test with
   node, when available) — all three must be **bit-exact** on quantized
   state; C++ RGB within ±2/255 of the Python float pipeline.
6. Bump `PROTOCOL_VERSION` if deployed devices could hold old firmware.

Golden files: `stream.bin` (wire bytes incl. SESSION), `expected.bin`
(per-frame quantized state), `expected_rgb.bin` (final strips via the float
reference **without** gamut clip — firmware clamps, spec §13.4), `meta.json`.

## 4. Quality gates

Per `plan/guidelines/code-quality.md`, every change: `black` immediately
after writing; `pytest` + `mypy` together. For 2.1 modules:

```bash
python -m pytest
python -m mypy luminary/geometry/coords.py luminary/geometry/lights.py \
  luminary/geometry/scaffold.py luminary/geometry/capture/ \
  luminary/geometry/pentagon/ luminary/color/convert.py \
  luminary/color/color.py luminary/comms/ luminary/engine/ \
  luminary/patterns/ luminary/render/ luminary/server/ \
  luminary/drivers/ luminary/cli.py \
  --explicit-package-bases --follow-imports=silent
```

`--follow-imports=silent` exists because pre-2.1 modules carry known mypy
debt — inventory in `plan/todo/legacy-mypy-debt.md`; clean it up as its own
branch, not inside feature diffs.

`tests/test_engine_integration.py::test_performance_budget_render_encode` is
a release gate (spec §17.3): render+encode for 8×256 lights must stay far
under the 33 ms frame budget.

## 5. Sharp edges discovered during implementation

- **Unanchored .gitignore template patterns eat project directories.** The
  stock Python packaging block (`lib/`, `build/`, `dist/`, …) matches at
  *any* depth: `lib/` silently excluded `firmware/scorpio/lib/` — the entire
  C++ decoder core was never committed, and `git add <dir>` skips ignored
  paths without a word. Those patterns are now root-anchored (`/lib/` etc.).
  If you add ignore rules, anchor anything that is a plausible source-tree
  name, and check with `git check-ignore -v <path>` / `git status --ignored`.
  (The loss was caught — and the restoration verified bit-exact — by the
  golden-vector conformance test, which is the kind of safety net worth
  keeping green.)
- **Hot reload vs. bytecode cache**: `importlib`'s `.pyc` validation keys on
  (mtime-seconds, size); a pattern file re-saved within one second at the
  same size would serve stale code. The registry therefore compiles source
  directly (`registry._load_file`). Don't "simplify" it back to
  `spec_from_file_location`.
- **Playwright in this container**: pip Playwright's bundled browser
  revision may not match `/opt/pw-browsers`; launch with
  `executable_path="/opt/pw-browsers/chromium"`.
- **Thin pentagon beams** can end behind their basis point; the pentagon
  capture clamps extents so an occlusion point is never behind the light
  (`pentagon/adapters.py`).
- **`Beam.forward_vector` is wrong-signed on clockwise-wound facets.** It
  is documented as "pointing into facet interior" but is a fixed
  counterclockwise perpendicular of the baseline, and most net triangles
  are wound clockwise. The pentagon capture referees with the beam
  polygon (authoritative — it is what the flat render draws) and mirrors
  the basis back through the anchor when the throw points away from the
  beam body; `test_beam_throw_points_into_its_own_facet` pins the
  physical statement. The upstream sign bug is still live for other
  callers of `forward_vector` / `get_basis_point()` /
  `generate_samples()` — fix it at source and the mirroring hunk in
  `pentagon/adapters.py` can delete itself.
- **`<option>` elements** inside a closed `<select>` are "hidden" to
  Playwright — wait with `state="attached"`.
- **Interpolation weights** are arc-length based (spec §6.2.3), not index
  fractions — tests cover the uneven-spacing case; don't regress to index
  math.

## 6. Runtime layout

- `store/` (gitignored): the server's content-addressed geometry store —
  `scaffolds/<id>.scaffold.json`, `lights/<id>.lights.json`,
  `patterns-uploads/`. Ships empty; ids are short SHA-1 content hashes, so
  identical saves dedupe. Stage demo data with `luminary.cli seed` (or
  `serve --seed-demo`) — idempotent by content hash — or via the API
  (`POST /api/scaffolds`, `POST /api/lights/from-scaffold`).
- Deployment (shared test server): `docs/deploy.md` — VPS/systemd path,
  Docker path, and the security model (pattern upload is in-process code
  execution; tailnet or authenticated proxy required).
- CI: `.github/workflows/ci.yml` runs pytest (incl. all three decoder
  conformance suites), plus black/mypy on the 2.1 module list.
- `examples/hex-demo.scaffold.json`: the standard demo scaffold (hexagon rim
  + six spokes, planar XY).
- `output/` (gitignored): 2.0 SVG outputs.
- Uploaded patterns execute **in-process** — trusted-operator model
  (spec §15.5.2, review §19.10).

## 7. Verified numbers (this implementation, commodity container)

- Render+encode, 2,048 active lights (kaleidoscope, budget 1200 B):
  **≈0.8 ms/frame** (budget: 33 ms; spec target ≤5 ms).
- Wire cost, 104-active hex demo at 30 fps, uncapped: ~1.3–2.6 B/light·frame
  by pattern; keyframe-every-frame floor is 2 B/light·frame.
- Pentagon (6,300 lights) budget-capped at 3,000 B/frame: **0.51
  B/light·frame** with no visible artifacts on smooth patterns.
- Browser client sustains 30 fps at 6,300 polygon lights (canvas, one strip
  decode per channel per frame).

Bitrate study, 2026-07-31 (4A-35 capture with physical addressing —
controller = 6 consecutive boards, channel = board; 600 frames at 30 fps,
keyframe interval 60; per-light rates measured at 180 lights/board and
projected linearly to a controller of six 360-LED boards = 2,160 active,
valid because a light's temporal statistics don't depend on neighbor
density):

- Uncapped wire cost across the nine repo patterns: **1.03–2.77
  B/light·frame** (firelike/plasma_storm low; spiral/wave high). Projected
  controller stream: 67–180 KB/s, vs 195.7 KB/s for RGB888 full refresh
  with identical framing (1.1–2.9×) and 130.6 KB/s for
  keyframe-every-frame.
- Uncapped, the encoder chases ±1-LSB rounding churn (spiral corrects 92%
  of lights every frame), so fast wide-field patterns approach keyframe
  cost; **the budget is the real operating point**: at 4,096 B/frame,
  spiral drops to 123 KB/s at ΔE_OKLab p95 0.010 (indistinguishable); at
  2,048 B/frame every repo pattern fits in ≤62.6 KB/s at p95 0.02–0.05,
  degrading as slight trailing on the fastest lights (error-ranked
  corrections), never as banding. Keyframes (budget-exempt) amortize to
  2.2 KB/s at the default 2 s interval; SESSION is ≈4.4 KB once.
- Color depth: steady-state 6/5/8 round-trip error mean ΔE_OKLab 0.006,
  max 0.011 (≈1 JND); keyframe instants (5/4/7 truncation) up to 0.032
  for one frame until deltas restore the low bits. 145,890 of 524,288
  grid cells (27.8%) are sRGB-representable; the rest is deliberate
  chroma headroom to C_MAX 0.4 for LED gamuts beyond sRGB. One delta word
  caps per-frame slew at 0.24 L / 0.09 C / 88.6° H.
- Finding: `patterns/firelike.py` renders C up to 0.45, which clips at
  wire C_MAX 0.4 (a constant ~0.05 ΔE on its most saturated lights).
  Patterns should stay within C ≤ 0.4 (README pattern how-to).

## 8. Deliberately deferred (with spec anchors)

- **Pentagon `{controller, channel, index}` routing** (review §19.6):
  round-robin placeholder in `pentagon/adapters.py::capture`. The physical
  strip path is now specified (plan/mapping/DESCRIPTION.md "The strip
  path": six-red corner → half-edge → radial in/out → finish the edge,
  three times around) and the mapping tool's wire hypothesis follows it;
  assigning capture identities along it awaits the per-board mapping
  YAMLs.
- **Camera-scan capture** (§7.4, review §19.9): `from_scan.py` defines the
  `ScanBundle` contract; the CV solver is a later milestone.
- **On-hardware firmware validation** (§13.6): the decoder core is
  host-tested bit-exact; NeoPXL8 output and the HELLO/RESYNC loop need a
  physical Scorpio. `main.cpp` has not been compiled against the Arduino
  toolchain in CI.
- **Multi-consumer single-engine mirroring** (§12.4): the server gives each
  WebSocket its own `Engine` (per-session predictor, trivially correct);
  broadcast-with-shared-encoder is designed (late joiners sync at the next
  keyframe) but not wired to the API.
- **Legacy patterns** (`patterns/legacy/`): `nudes2`, `rectangle_prisms`
  await stateless rework (see `patterns/legacy/README.md`;
  `patterns/plasma_storm.py` is the worked example of the conversion).
- **Legacy mypy debt**: `plan/todo/legacy-mypy-debt.md`.

## 9. History

- 2.0 (pentagon SVG + JSON-per-frame preview) → spec review →
  `plan/spec/luminary-2.1-spec.md` (PR #7) → full implementation (PR #8,
  stacked). The spec's §3 ledger records every keep/refactor/rewrite/new
  decision with rationale; §19 records the review resolutions.
