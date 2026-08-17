# Luminary 2.1 — Detailed System Specification

> Status: **DRAFT FOR REVIEW.** This document supersedes the prose brief and the
> scattered `plan/` notes as the authoritative design for the 2.1 production
> release. It is written so that every paragraph is individually addressable
> (e.g. "§11.4.3") for line-by-line review. Nothing here is implemented yet;
> the existing 2.0 code is treated as raw material, not as a constraint.

---

## 1. Purpose, Scope, and Design Principles

### 1.1 Purpose

1.1.1 Luminary drives a physical light installation: a rigid **scaffold** of
structural lines onto which many individually-addressable RGB LEDs ("lights")
are mounted. The system computes, every frame, a color for every light from a
chosen **pattern**, and streams those colors to the hardware that lights them.

1.1.2 The same computational core must serve three consumers without
duplicated logic: (a) the **production** path — driving Adafruit Scorpio
microcontrollers over a serial wire; (b) a **debug/demo** path — driving a web
browser over WebSockets; and (c) **authoring** paths — static rendering and
geometry tooling. All three are *adapters* over one engine.

### 1.2 Scope of 2.1

1.2.1 In scope: scaffold geometry format + loader; lights geometry format +
loader + saver; lights capture from scaffold (with defaults); a vectorized
color subsystem; the pattern contract + registry + hot-reload; the
transport-agnostic engine; the bit-efficient wire protocol (codec) with a
reference decoder; a serial driver; Scorpio firmware; a web server exposing the
required API; a Canvas-based web client that decodes the wire protocol; the CLI.

1.2.2 Out of scope for 2.1 (interfaces defined, implementation deferred):
camera-based light-position scanning (the capture *interface* is specified in
§7.4, the computer-vision implementation is a later milestone); multi-controller
time synchronization beyond a shared clock; audio reactivity; any non-Python
rewrite (Rust/C ports are explicitly deferred — see §1.3.5).

### 1.3 Design Principles (binding)

1.3.1 **One engine, one way.** There is exactly one core engine and one
canonical representation of each thing (one scaffold model, one lights array,
one color pipeline, one codec). Different ways to *trigger* rendering, *feed* it
geometry, or *emit* frames are adapters around the engine, never parallel
re-implementations. Concretely: the WebSocket demo and the serial production
path MUST share the same encoder and the same frame source (§2, §12).

1.3.2 **The production path is exercised continuously.** Because the demo path
uses the identical codec and engine as the hardware path, day-to-day browser
testing also tests production. We never let the hardware path rot behind an
untested abstraction.

1.3.3 **Vectorize everything per-frame and per-light.** Any operation repeated
across the set of lights on the hot path (pattern evaluation, color conversion,
prediction, quantization, error scoring) MUST be expressed as NumPy column
operations over the lights array — never a Python per-light loop. Per-light
Python loops are permitted only in one-time load/capture code, and even there
should be avoided where practical.

1.3.4 **Stateless rendering.** A pattern's output is a pure function of the
lights array and a time variable `t` (float seconds). Any frame can always be
recomputed from its `t` alone, with no dependence on prior frames. This property
is relied upon by the codec (the encoder can always recompute ground truth at
`t`; keyframes resynchronize deterministically) and by replay/testing.
Cross-language conformance is defined on encoded bytes and quantized integers
(§11), never on float results, so float `t` does not threaten determinism.

1.3.5 **Modular, contract-first, Rust-ready (but Python now).** Each component
is defined by a narrow data contract (NumPy arrays, byte buffers, JSON) so that
any single component — most likely the codec or the color pipeline — could later
be replaced by a compiled implementation without touching its neighbors. For
2.1, everything server-side is Python; the Scorpio firmware is C++ (§13.1).

1.3.6 **Hot-swappable specs and code.** Geometry files and pattern files are
reloadable at runtime without restarting the engine (§9.3, §15.5).

1.3.7 **DRY across language boundaries.** Where a contract must be implemented
in more than one language (the decoder exists in Python, JavaScript, and C++),
there is a single normative definition (this spec + a Python reference
implementation) and the others are verified against shared golden vectors
(§11.9). We accept multiple *conformant implementations* of one spec; we do not
accept divergent designs.

---

## 2. System Architecture Overview

### 2.1 The pipeline

2.1.1 The end-to-end data flow, left to right:

```
 Scaffold spec ─┐
                ├─▶ Lights capture ─▶ Lights geometry ─┐
 (camera scan) ─┘        (§7)            (§6)           │
                                                        ▼
              Pattern (§9) ─▶ ┌─────────────────────────────────┐
              t (seconds) ─▶ │           ENGINE (§10)            │
                             │  lights_array, pattern, t  →      │
                             │  OKLCH array  →  Codec.encode (§11)│
                             └───────────────┬─────────────────┘
                                             │  wire frames (bytes)
                            ┌────────────────┼─────────────────┐
                            ▼                ▼                  ▼
                   Serial driver (§12)  WS driver (§12)    (golden vectors)
                            │                │
                            ▼                ▼
                   Scorpio firmware    Browser client
                   decode→interp→      decode→interp→
                   RGB→NeoPXL8         RGB→Canvas
                        (§13)               (§14)
```

2.1.2 **Engine output is wire frames, not colors.** The engine's per-frame
product is a sequence of encoded byte frames produced by the codec. Both the
serial and WebSocket drivers consume these identical bytes. This is the
mechanism that makes §1.3.1/§1.3.2 true rather than aspirational.

2.1.3 The browser is therefore a *decoder*, not a privileged client receiving
pre-rendered colors. It runs the same decode → interpolate → OKLab → gamma-RGB
pipeline that the Scorpio firmware runs, so the demo validates the protocol.

### 2.2 Module layout

2.2.1 Proposed Python package layout (new/renamed modules called out in §3):

```
luminary/
  geometry/
    coords.py        # vectorized coordinate-system conversions (§4)
    scaffold.py      # Scaffold model + JSON loader/saver (§5)
    lights.py        # LightsGeometry: canonical array + schema + IO (§6)
    capture/
      from_scaffold.py  # default line-based capture (§7.2)
      from_scan.py      # camera-scan interface (stub, §7.4)
    primitives.py    # Point/Vector/Segment/Ray/Line (kept, load-time only)
    pentagon/        # existing Net/Triangle/Facet/Beam, demoted (§3, §7.3)
  color/
    convert.py       # vectorized OKLab/OKLCH <-> linear sRGB <-> sRGB8 (§8)
    color.py         # scalar Color, for config parsing only (§8.5)
  patterns/
    base.py          # Pattern ABC (§9.1)
    registry.py      # discovery + hot reload (§9.3)
    *.py             # individual patterns
  engine/
    engine.py        # transport-agnostic core (§10)
  comms/
    protocol.py      # constants, framing, quantization tables (§11)
    codec.py         # Encoder + reference Decoder (§11)
    predictor.py     # shared dead-reckoning predictor (§11.5)
  drivers/
    serial_driver.py     # engine → serial (§12.2)
    websocket_driver.py  # engine → websocket (§12.3)
  render/
    projection.py    # world → 2D screen layout, shared by SVG + Canvas (§14.4)
    svg.py           # static SVG renderer (§14.5)
  server/
    app.py           # FastAPI app: REST + WS (§15)
    store.py         # on-disk geometry/pattern store (§15.6)
    static/          # web client assets (HTML/JS/CSS) (§14)
  cli.py             # unified CLI entry (§16)
firmware/
  scorpio/           # Arduino C++ project (NeoPXL8) (§13)
  golden/            # shared codec conformance vectors (§11.9)
```

2.2.2 Dependency direction is strictly inward: `server` and `drivers` depend on
`engine`; `engine` depends on `geometry`, `patterns`, `color`, `comms`;
`comms`, `color`, `geometry`, `patterns` depend on nothing above them and never
import `server`/`drivers`. The engine MUST NOT import any web framework.

---

## 3. Component Disposition Ledger

3.0.1 This section states, per existing component, whether 2.1 will **Keep**
(use largely as-is), **Refactor** (restructure but reuse logic), **Rewrite**
(replace the implementation, keep the idea), or build **New**. Rationale is
given so each decision can be contested individually.

| # | Component (2.0) | Disposition | Rationale |
|---|---|---|---|
| 3.1 | `patterns/base.py` `LuminaryPattern.evaluate(array,t)->OKLCH` | **Keep** (tighten contract) | Vectorized pure-function model is exactly right (§1.3.3/1.3.4). `t` stays float seconds (§9.1, review §19.1); rename to `render` for clarity; keep semantics. |
| 3.2 | `patterns/schema.py` `BeamArrayColumns` (11 cols) | **Refactor → Rewrite** | Generalize to the lights-array schema with full coordinate set, identity `{controller,channel,index}`, and metadata (§6.3). The 11-column layout is too 2D/pentagon-specific. |
| 3.3 | `patterns/beam_array.py` `BeamArrayBuilder` | **Rewrite** | Becomes part of lights capture (§7) and the `LightsGeometry` loader (§6). Per-light Python loop replaced with vectorized assembly. Placeholder hardware mapping replaced by real identity columns. |
| 3.4 | `patterns/discovery.py` | **Refactor** | Good concept; fold into `patterns/registry.py` with real hot-reload (`importlib.reload`), error isolation, and a stable registry object (§9.3). |
| 3.5 | example patterns (`example_*.py`, `kaleidoscope`, etc.) | **Keep/Port** | Keep as a test corpus; port to the new column enum (`t` semantics unchanged: float seconds). Stateful ones are reworked to be stateless or parked under `patterns/legacy/`. They are valuable coverage for the engine and codec. |
| 3.6 | `color/oklch.py` `Color` (via `colour` lib) | **Rewrite** | Per-object + `colour` dependency is unusable on the per-frame, per-light hot path. Replace with vectorized `color/convert.py` (§8); keep a thin scalar `Color` for parsing config color names only (§8.5). Drop `colour-science` dependency. |
| 3.7 | `geometry/primitives.py`, `point.py` | **Keep** (load-time only) | Solid for capture/authoring math. Forbid from the hot path. Apply the existing `plan/todo/refactor.md` cleanup opportunistically, not as a 2.1 gate. |
| 3.8 | `geometry/net.py`,`triangle.py`,`facet.py`,`beam.py` | **Refactor → Demote** | Move under `geometry/pentagon/`. Repurpose as (a) a **scaffold generator** that emits scaffold lines and (b) a **capture** that emits a default lights geometry, and (c) the diagnostic SVG diagram. Beam *polygons* become a render-only detail; "beam basis point" becomes a light position. Not on the per-frame core path. |
| 3.9 | `config/schema.py` (Pydantic `NetConfiguration`) | **Refactor** | Keep Pydantic validation; split into a `scaffold` schema (§5) and a `lights` schema (§6); retain the pentagon config schema under the pentagon module for back-compat with `configs/*.json`. |
| 3.10 | `writers/svg/*` | **Keep/Refactor** | Reuse SVG primitive emitters; drive them from the new `render/projection.py` so SVG and Canvas share one projection (§14.4). |
| 3.11 | `patterns/webserver/server.py` | **Rewrite** | Replace ad-hoc JSON-per-beam framebuffer with the API of §15 and the wire codec of §11. |
| 3.12 | `patterns/webserver/client.html` | **Rewrite** | Replace per-element SVG fill updates with a Canvas renderer + JS decoder (§14). |
| 3.13 | `main.py` CLI | **Refactor** | Re-express subcommands as thin adapters selecting a driver over the one engine (§16). Keep `validate`/`svg`/`index` utilities. |
| 3.14 | `validation/validate.py` | **Keep** | Useful visual self-tests; extend to cover scaffold/lights rendering. |
| 3.15 | Serial protocol / codec | **New** | §11. The core novelty of 2.1. |
| 3.16 | Scorpio firmware | **New** | §13. |
| 3.17 | Scaffold & lights geometry formats + capture | **New** | §5–§7. |
| 3.18 | On-disk store + full web API | **New** | §15. |

3.19.1 Net effect: the *idea* layer of 2.0 (vectorized patterns, OKLCH, JSON
geometry, SVG preview, pentagon art) is preserved; the *hot-path
implementations* (color, array build, wire format, client) are rewritten for
performance and hardware; and the genuinely missing pieces (scaffold/lights
abstraction, codec, firmware, real API) are built new.

---

## 4. Coordinate Systems and Geometry Conventions

### 4.1 The four coordinate spaces

4.1.1 Every positioned entity (scaffold endpoint, scaffold normal, light) may be
expressed in up to four coordinate spaces, per the brief:

- **XY projection** `(x, y)` — the 2D "drawing" projection used for SVG/Canvas
  and for planar installations. This is the authoritative space for 2D work.
- **XYZ spatial** `(x3, y3, z3)` — true 3D position. Authoritative for 3D work.
- **r-θ projection** `(r, theta)` — polar form of the XY projection
  (`r=hypot(x,y)`, `theta=atan2(y,x)`), `theta` in radians.
- **θ-φ spherical** `(theta_s, phi_s)` and radius `rho` — spherical form of the
  XYZ spatial position.

4.1.2 **Authoritative vs derived.** A geometry file declares which space(s) are
*authoritative* (directly specified). All other spaces are *derived* at load
time by `geometry/coords.py` (§4.3). A planar installation specifies only XY;
XYZ is then `z3=0`, spherical degenerate. A 3D installation specifies XYZ; the
XY projection is produced by a declared projection (§4.2).

4.1.3 Patterns read whichever columns they need. Columns for a space that is
neither authoritative nor derivable are filled with `NaN`, and a pattern that
reads them is responsible for tolerating `NaN` (helpers in §9.4).

### 4.2 Projection from 3D to 2D

4.2.1 When XYZ is authoritative, the XY projection is computed by a **named
projection** declared in the geometry file. v2.1 supports: `orthographic_xy`
(drop z), `orthographic_xz`, `orthographic_yz`, and `spherical_equirect`
(map `(theta_s,phi_s)`→`(x,y)`). Projections are pure functions in `coords.py`
so new ones are added in one place.

4.2.2 The projection used for capture/preview is recorded in the lights file so
the web/SVG renderers reproduce the same 2D layout deterministically.

### 4.3 `coords.py` contract

4.3.1 `coords.py` exposes vectorized functions operating on `(n,·)` arrays only,
e.g. `xy_to_polar(xy)->rtheta`, `xyz_to_spherical(xyz)->(rho,theta,phi)`,
`project(xyz, name)->xy`, and a single `derive_all(authoritative_columns,
projection) -> full_coordinate_block` used by both the scaffold and lights
loaders so the derivation rule lives in exactly one place (§1.3.1).

4.3.2 Angles are radians internally everywhere; degrees appear only at file and
UI boundaries and are converted at those boundaries.

### 4.4 Normals and direction

4.4.1 A **normal** is a unit 3-vector pointing *away from the scaffold line, to
one side of it, lying along the manifold surface* (the brief). It is a lateral
in-surface direction that distinguishes the two sides of the line on the
surface — NOT a surface normal (it does not point out of the manifold). On a
planar manifold a straight line has a single normal per side (in-plane,
perpendicular to the line), so all three sampled normals of a line are equal;
on curved manifolds the normal varies along the line, which is why a line
carries normals at three sample points (§5). Lights mounted on a line shine
along this direction — across the surface, away from the line — which is
exactly the pentagon "beam" concept generalized.

4.4.2 A light **direction** is a unit 3-vector giving the axis the light emits
along, plus an **extent**: the farthest point reachable along that direction
before occlusion (the brief). Extent is stored as a 3D point `(ex,ey,ez)`;
the scalar throw distance is derived as `|extent - position|`. Direction and
extent are optional; absent ⇒ `NaN` (a light with no modeled aim).

---

## 5. Scaffold Geometry

### 5.1 Concept

5.1.1 A **scaffold** is the set of structural lines of the installation. It is
authored/derived independently of the lights; lights are later placed onto it
(§7). Scaffold geometry is what the web "render a scaffold" view draws as the
skeleton, and the substrate the default capture walks.

### 5.2 Line model

5.2.1 A scaffold **line** is specified by: two endpoints `p1`, `p2`; an optional
explicit `midpoint` (needed on non-planar manifolds where the line is not a
straight chord — absent ⇒ derived as the average of `p1,p2`); and three normals
`n1`, `n_mid`, `n2` at `p1`, midpoint, and `p2` respectively (the brief's "three
normals"; on a planar manifold all three are equal).

5.2.2 Endpoints and normals are each given in the file's authoritative
coordinate space(s) (§4.1.2). Lines may carry an optional `id` (string) and
optional `tags` (list of strings) for grouping/overrides (used by capture, §7).

### 5.3 File format (`*.scaffold.json`)

5.3.1 Pydantic-validated JSON:

```jsonc
{
  "schema": "luminary.scaffold/1",
  "space": { "authoritative": ["xy"],         // or ["xyz"], or ["xyz","xy"]
             "projection": "orthographic_xy", // required iff xyz is authoritative
             "angle_units": "deg" },          // deg|rad at file boundary only
  "lines": [
    { "id": "edge-12",
      "p1": [x, y /*, z*/], "p2": [x, y /*, z*/],
      "midpoint": [x, y /*, z*/],             // optional
      "n1": [nx, ny, nz], "n_mid": [...], "n2": [...],  // optional (§5.3.2 default)
      "tags": ["ring0"] }
  ],
  "meta": { "name": "...", "notes": "..." }   // optional, free-form
}
```

5.3.2 Defaults: on a planar (`["xy"]`) scaffold, `z=0` and `midpoint` defaults
to the chord midpoint. Normals default to the in-plane lateral direction
obtained by rotating the unit `p1→p2` direction +90° counterclockwise (§4.4.1);
a file that cares which side the lights face specifies normals explicitly. The
loader rejects a file that declares `xyz` authoritative without a `projection`.

### 5.4 Loader/saver contract

5.4.1 `scaffold.load(path|dict) -> Scaffold` validates, converts angle units,
and derives all coordinate spaces (§4.3.1) for endpoints, midpoints, and
normals. `scaffold.save(Scaffold, path)` round-trips losslessly in the
authoritative space.

5.4.2 `Scaffold` exposes vectorized arrays for renderers and capture:
`endpoints_xy -> (n_lines,2,2)`, `normals_xyz -> (n_lines,3,3)`, plus the raw
line list for id/tag lookups. No per-frame code touches `Scaffold`; it is a
load/author-time object.

### 5.5 Pentagon as a scaffold source

5.5.1 The existing pentagon `Net` is refactored (§3.8) to emit a `Scaffold`: its
geometric lines (`config.lines` / triangle edges) become scaffold lines in XY,
with planar normals. This preserves all existing `configs/*.json` as valid
inputs via a `pentagon.to_scaffold(net)` adapter, satisfying DRY rather than
inventing a second pentagon format.

---

## 6. Lights Geometry (the canonical representation)

### 6.1 Concept

6.1.1 The **lights geometry** is the single canonical input the engine and all
patterns consume. It is a table with one row per light, carrying identity,
metadata, full coordinates, direction/extent, and normal. In memory it is one
contiguous `float64`/`float32` NumPy array (the **lights array**); on disk it is
JSON (§6.5). Everything downstream (patterns, codec, renderers) is defined in
terms of this array. There is no other per-light representation (§1.3.1).

### 6.2 Identity and metadata

6.2.1 A light is uniquely identified by `{controller, channel, index}` (the
brief): `controller` = which Scorpio board; `channel` ∈ [0,8) = which of the
Scorpio's eight strip outputs; `index` = position along that strip. This triple
is the wire address (§11) and the firmware buffer address (§13).

6.2.2 Each light has a **kind**: `ACTIVE` (0) — individually controlled and
transmitted; `INTERPOLATED` (1) — not transmitted; reconstructed on-device by
interpolating between the nearest ACTIVE lights on the same channel (§13.5);
`INACTIVE` (2) — not controlled and not lit (skipped/blacked). Kind drives both
bandwidth (only ACTIVE lights hit the wire) and firmware behavior.

6.2.3 Interpolated lights carry an interpolation **weight** `w ∈ [0,1]`: their
fractional position between the bounding ACTIVE lights, measured by physical
distance along the strip (not index spacing), so uneven spacing interpolates
correctly. `w` is precomputed at load (§6.6).

### 6.3 Lights array column schema

6.3.1 Column order is defined once as an `IntEnum` `LightColumns` in
`geometry/lights.py` and imported everywhere (no magic indices, §1.3.7). The
canonical columns:

| Idx | Name | Type/units | Meaning |
|----|------|-----------|---------|
| 0 | `CONTROLLER` | int | board id |
| 1 | `CHANNEL` | int 0–7 | Scorpio output |
| 2 | `INDEX` | int | position on strip |
| 3 | `KIND` | int enum | 0 active / 1 interp / 2 inactive |
| 4 | `WEIGHT` | float 0–1 | interp weight (NaN if not interp) |
| 5 | `X` | float | XY projection x |
| 6 | `Y` | float | XY projection y |
| 7 | `R` | float | polar r |
| 8 | `THETA` | float rad | polar θ |
| 9 | `X3` | float | spatial x |
| 10 | `Y3` | float | spatial y |
| 11 | `Z3` | float | spatial z |
| 12 | `RHO` | float | spherical radius |
| 13 | `THETA_S` | float rad | spherical θ |
| 14 | `PHI_S` | float rad | spherical φ |
| 15 | `DX` | float | direction unit x |
| 16 | `DY` | float | direction unit y |
| 17 | `DZ` | float | direction unit z |
| 18 | `EX` | float | extent point x |
| 19 | `EY` | float | extent point y |
| 20 | `EZ` | float | extent point z |
| 21 | `NX` | float | normal x |
| 22 | `NY` | float | normal y |
| 23 | `NZ` | float | normal z |

6.3.2 Unavailable derived coordinates are `NaN` (§4.1.3). Integer-semantics
columns (0–3) are stored as float in the array but always hold integral values;
a typed accessor returns them as `int` arrays when needed by the codec.

6.3.3 The array is the contract; its column *count* may grow in later schema
versions (append-only), so code MUST index by `LightColumns`, never by literal
or by `array.shape[1]`.

### 6.4 Ordering invariant

6.4.1 Rows are sorted by `(controller, channel, index)`. This ordering is the
same order the codec walks (§11.3) and the firmware addresses, so encoder and
decoder never exchange explicit addresses for in-order runs — only deltas
(§11.4). The loader enforces and records this sort.

### 6.5 File format (`*.lights.json`)

6.5.1 Pydantic-validated JSON, authoritative-space mirroring the scaffold
(§5.3.1):

```jsonc
{
  "schema": "luminary.lights/1",
  "space": { "authoritative": ["xy"], "projection": "orthographic_xy",
             "angle_units": "deg" },
  "source": { "type": "from_scaffold", "scaffold": "<id-or-inline>",
              "params": { ... } },        // provenance (§7); free for hand-authored
  "lights": [
    { "controller": 0, "channel": 0, "index": 0,
      "kind": "active",
      "pos": [x, y /*, z*/],
      "dir": [dx, dy, dz], "extent": [ex, ey, ez],   // optional
      "normal": [nx, ny, nz],                         // optional
      "display": [[x,y], [x,y], ...] }                // optional 2D polygon (§6.5.3)
    // interpolated lights may omit pos (derived) but must give controller/channel/index
  ],
  "meta": { "name": "...", "notes": "..." }
}
```

6.5.2 The file stores only authoritative quantities; derived coordinate spaces,
interpolation weights, and the row sort are reconstructed by the loader so the
file stays minimal and human-diffable.

6.5.3 **Display shapes.** A light may carry an optional `display` polygon (XY
space): a render-only hint that preview surfaces (SVG and the web client) draw
instead of a generic dot. This is how beam polygons survive as a *display*
concept (per review of §19.5): the pentagon constructor emits each light's beam
polygon here. Display shapes live beside the numeric array (never in it), are
ignored by the codec/firmware entirely, and are served to the web client via
the layout endpoint (§15.3).

### 6.6 Loader/saver contract

6.6.1 `lights.load(path|dict) -> LightsGeometry`: validates; converts units;
derives all coordinate spaces vectorized (§4.3.1); computes interpolation
weights for INTERPOLATED lights from along-strip distance between bounding
ACTIVE lights; sorts rows (§6.4); returns an object wrapping the lights array
plus the per-channel interpolation map (§13.5) and convenience accessors.

6.6.2 `lights.save(LightsGeometry, path)` writes the authoritative-space JSON.
`LightsGeometry.array` is the NumPy lights array; `.control_mask` is a boolean
`(n,)` selecting ACTIVE rows (used pervasively by the codec).

6.6.3 Validation errors are precise and actionable (duplicate
`{controller,channel,index}`; INTERPOLATED light with no bounding ACTIVE lights
on its channel; channel ≥ 8; etc.).

---

## 7. Lights Capture (scaffold → lights)

### 7.1 Concept and the one exit-condition method

7.1.1 **Capture** produces a lights geometry. The brief lists three sources:
(a) assigning light ids to points on scaffold lines plus some free assignment;
(b) a camera lighting-scan; (c) future methods. The exit condition "produce a
lights geometry from a scaffold + simple defaults" is method (a). It is the only
capture fully implemented in 2.1; (b) gets an interface (§7.4).

### 7.2 Default capture: lights along scaffold lines (`from_scaffold`)

7.2.1 Input: a `Scaffold` and a `params` dict. Output: a `LightsGeometry`.

7.2.2 Algorithm (deterministic, vectorized where it spans lights):
for each scaffold line, place lights at a configured spacing (or fixed count)
from `p1` toward `p2`; each light's position is the parametric point on the line
(using `midpoint` for a quadratic bend when present), its normal is the
correspondingly-interpolated `n1/n_mid/n2`, its direction defaults to that
normal — i.e., the light throws across the surface, away from its line (§4.4.1)
— and extent is `position + throw_distance·direction` when a throw distance is
given, else `NaN`.

7.2.3 Identity assignment: `params` maps lines (by `id`/`tag`/order) to
`(controller, channel)` and a starting `index`; lights along a line receive
consecutive indices. A "simple defaults" mode assigns channels round-robin
across lines and a single controller, producing a valid (if not
hardware-faithful) lights geometry for preview.

7.2.4 Interpolation policy: `params.interpolate_every = k` marks every light
whose along-channel position is not a multiple of `k` as INTERPOLATED (so only
1-in-`k` lights are transmitted), or `interpolate: false` makes all lights
ACTIVE. This is how the operator trades bandwidth for fidelity at capture time;
the codec then also adapts at run time (§11.6).

7.2.5 Free assignment: `params.extra_lights` is a list of hand-placed lights
(explicit position + identity) merged into the result, covering the brief's
"plus assigning some of them freely."

### 7.3 Pentagon capture (compatibility)

7.3.1 `pentagon.capture(net, params)` reproduces today's behavior: each beam's
basis point becomes one ACTIVE light, its direction is the beam's forward
direction (anchor → basis, i.e., the in-surface normal of its edge, §4.4.1) and
its extent is the far end of the beam polygon along that direction. The beam
polygon itself is attached as the light's `display` shape (§6.5.3), so beams
remain a first-class concept of this *constructor* and of the web frontend's
rendering — but not of the core engine. The `{controller,channel,index}`
mapping from `{face,facet,edge,position}` is **deferred** pending hardware
strip-routing decisions (review §19.6): until then capture assigns channels
round-robin per facet and sequential indices, which is valid for preview and
demo, and the mapping function is the single documented place to change when
the physical routing is known.

### 7.4 Camera scan interface (deferred implementation)

7.4.1 Defined now so the data contract is stable: `from_scan` consumes a
**scan bundle** — a set of captured frames each tagged with the
`{controller,channel,index}` that was lit, plus camera intrinsics/pose — and
produces, per light, a 2D image position lifted to scaffold-relative 3D by
intersecting the camera ray with the nearest scaffold line. Output is a normal
`LightsGeometry` (§6). 2.1 ships the interface, the bundle format, and a stub
that errors with "not implemented"; the CV solver is a later milestone. This
keeps method (b) a drop-in alternative to method (a), never a parallel pipeline.

---

## 8. Color Subsystem

### 8.1 Why a rewrite

8.1.1 The 2.0 `Color` class allocates a Python object per color and routes
through the `colour` library — acceptable for parsing a few config colors,
unacceptable for converting thousands of lights every frame. 2.1 adds a
vectorized module and reserves the scalar class for parsing only (§3.6).

### 8.2 Spaces and the canonical pipeline

8.2.1 Patterns output **OKLCH** `(L, C, H)` — `L∈[0,1]`, `C∈[0,~0.4]`,
`H` in degrees `[0,360)`. OKLCH is the engine's interchange color and what the
codec quantizes (§11.4), because it is perceptually uniform (good for
quantization and prediction) and device-independent.

8.2.2 Interpolation between control lights happens in **OKLCH with
shortest-arc hue** (review §19.3): L and C interpolate linearly; H interpolates
along the shorter direction around the hue circle. This operates directly on
the decoded (quantized) OKLCH state, so interpolation needs no color-space
conversion. **OKLab** `(L,a,b)` (`a=C·cos H`, `b=C·sin H`) remains the
conversion intermediate on the way to RGB (§8.4).

8.2.3 Output is **gamma-encoded sRGB8** for the LEDs/Canvas. The full chain
OKLab → linear sRGB → gamma sRGB is in §8.4.

### 8.3 Vectorized API (`color/convert.py`)

8.3.1 All functions take and return `(n,3)` arrays and contain no Python loops:
`oklch_to_oklab`, `oklab_to_oklch`, `oklab_to_linear_srgb`,
`linear_srgb_to_oklab`, `linear_to_srgb8` (gamma encode + clamp/round to uint8),
`srgb8_to_linear`, and the convenience `oklch_to_srgb8`. A `gamut_clip` option
maps out-of-gamut OKLab to the nearest in-gamut color by reducing chroma at
fixed L,H (documented, deterministic) rather than naive per-channel clamping.

### 8.4 Normative constants

8.4.1 OKLab uses Björn Ottosson's matrices. Decode (the firmware/JS hot path),
OKLab→linear sRGB:

```
l_ = L + 0.3963377774*a + 0.2158037573*b
m_ = L - 0.1055613458*a - 0.0638541728*b
s_ = L - 0.0894841775*a - 1.2914855480*b
l = l_^3 ; m = m_^3 ; s = s_^3
r =  4.0767416621*l - 3.3077115913*m + 0.2309699292*s
g = -1.2684380046*l + 2.6097574011*m - 0.3413193965*s
b' = -0.0041960863*l - 0.7034186147*m + 1.7076147010*s
```

8.4.2 sRGB gamma encode per channel `c∈[0,1]`:
`s = 12.92*c` if `c ≤ 0.0031308` else `1.055*c^(1/2.4) − 0.055`; then
`round(255*clamp(s,0,1))`. The forward (encode) matrices are the documented
inverses; they live beside the decode constants so all three language
implementations cite one source (§1.3.7).

8.4.3 An optional per-light global **brightness** scalar and per-channel LED
**color-correction** (e.g. WS2812 white balance) are applied in linear sRGB
before gamma, configured per controller in the lights/firmware config.

### 8.5 Scalar `Color` (parsing only)

8.5.1 `color/color.py` keeps `Color.from_string` for `"#RRGGBB"` and
`"oklch(...)"` used by config color tables (scaffold/pentagon files). It is a
thin wrapper that calls `convert.py` on a length-1 array. It MUST NOT be used on
the per-frame path; a comment and (in tests) a guard enforce this.

---

## 9. Patterns

### 9.1 Contract

9.1.1 `patterns/base.py` defines:

```python
class Pattern(ABC):
    name: str            # class attribute or property
    description: str
    def render(self, lights: np.ndarray, t: float) -> np.ndarray: ...
```

9.1.2 `lights` is the lights array (§6.3); `t` is **elapsed time in seconds as
a float** (review §19.1). Return is an `(n,3)` float array of OKLCH for *all*
rows (active, interpolated, inactive); the engine selects what to transmit
(§10.3). Output must be finite for non-`NaN` inputs.

9.1.3 The function MUST be vectorized and stateless: no instance mutation across
calls, no dependence on previous `t`. Determinism: `render(lights,t)` is
reproducible; any randomness must be a pure function of `t` and a fixed seed
(helper provided, §9.4) so the server can recompute any frame for the codec.

9.1.4 The engine owns the frame rate (default 30 fps) and passes patterns
`t = frame_index / fps` when it is the pacer; patterns simply see seconds.
Integer frame counters exist only inside the engine/codec (keyframe cadence,
budgets) and never in the pattern contract. Replay and golden vectors remain
exact because conformance is defined on encoded bytes (§11.9), and the encoder
records the `t` of every frame in its header (§11.7.5).

### 9.2 Idiom

9.2.1 Signed distance functions over the coordinate columns are the encouraged
idiom (and the existing patterns are good examples), but the contract is "any
pure vectorized OKLCH function," not literally an SDF — so we don't constrain
authors needlessly while keeping one return type.

### 9.3 Registry and hot-reload

9.3.1 `patterns/registry.py` discovers `Pattern` subclasses from a patterns
directory (default `patterns/`, plus an uploads dir, §15.5). `reload()`
re-imports changed modules via `importlib`, isolating exceptions so one broken
file does not crash the engine; it reports per-file load errors. The registry is
the single source of "available patterns" for the CLI and the API (§15.5).

9.3.2 A pattern is referenced by a stable `name`. Hot-swapping the running
pattern is an engine operation (§10.4) that takes effect at the next frame
boundary; because rendering is stateless, no transition state is needed.

### 9.4 Author helpers

9.4.1 `patterns/util` offers vectorized helpers: `seeded_random(salt, n)` (for
deterministic per-light constants), `nan_safe` wrappers, hue helpers, and
named-column accessors (`X(lights)`), so patterns never hardcode column indices
(§6.3.3).

---

## 10. Core Engine

### 10.1 Role

10.1.1 `engine/engine.py` is the transport-agnostic core (the brief: "the core
engine, completely agnostic of webserver code; it only performs the geometry
operations or loads lights geometries to play patterns that it streams out").
It holds a `LightsGeometry`, a current `Pattern`, an `Encoder` (§11), and the
tick clock; it produces encoded wire frames. It imports no web/serial code.

### 10.2 Construction and lifecycle

10.2.1 `Engine(lights: LightsGeometry, pattern: Pattern, *, fps=30.0,
codec_config=CodecConfig())`. Methods: `set_pattern(Pattern)`,
`set_lights(LightsGeometry)` (both trigger a codec keyframe, §11.7),
`session_frames() -> list[bytes]` (one SESSION per controller),
`frame(t: float) -> list[bytes]` (one encoded frame per controller), and
`frames(start=0) -> iterator` yielding `(t, list[bytes])` as fast as pulled —
pacing belongs to drivers.

10.2.2 `frame(t)` is the one place the pipeline is assembled:
`oklch = pattern.render(lights.array, t)` → `wire = encoder.encode(oklch, t)`.
Both drivers call exactly this; there is no second assembly site (§1.3.1).

### 10.3 Selection of transmitted lights

10.3.1 The pattern computes OKLCH for all rows; the encoder transmits only
ACTIVE rows (`lights.control_mask`), in canonical order (§6.4). INTERPOLATED and
INACTIVE rows never reach the wire. This split is the engine's, not the
pattern's, so patterns stay purely about color.

### 10.4 Statelessness and reconfiguration

10.4.1 The only engine state is the codec's predictor state (the *encoder's
model of the decoder*, §11.5) plus the current pattern/lights selection.
Changing pattern or lights, or a decoder requesting resync, forces a keyframe;
otherwise frame production is a pure function of `t`. This makes the engine
trivially restartable and testable.

### 10.5 Non-encoded outputs (authoring)

10.5.1 For static rendering and the geometry-preview views (which show color
without the wire), the engine also exposes `colors_srgb8(t) -> (n,3) uint8`
(pattern → `convert.oklch_to_srgb8`) so the SVG/Canvas *static* paths reuse the
same pattern+color code without going through the codec. Live playback always
goes through the codec (§14.3).

---

## 11. Wire Comms Protocol (the Codec)

> This is the central new subsystem and the highest-risk area. The wire format
> (§11.4) and predictor arithmetic (§11.5.4) were fixed at spec review, so the
> full codec — keyframes *and* dead-reckoning deltas — is implemented as one
> module from the start. A keyframe-every-frame configuration (budget=∞,
> interval=1) remains available as the obviously-correct debug baseline; delta
> budgets and cadence are the tunables (§18.6).

### 11.1 Goals (from the brief, made testable)

11.1.1 Minimize bits per light per update. 11.1.2 Be *eventually correct*, not
necessarily per-frame lossless (drift is bounded and erased by keyframes).
11.1.3 Be adaptive: spend more bits for fidelity when bandwidth allows, fewer
when constrained. 11.1.4 Keyframe to bound drift. 11.1.5 Be identical across the
serial and WebSocket paths and across Python/JS/C++ implementations (§11.9).

### 11.2 Channel-sharded model

11.2.1 The wire is organized per `(controller, channel)`. Each channel is an
ordered run of ACTIVE lights (by `index`). Sharding lets the firmware update one
NeoPXL8 channel's buffer independently and lets the encoder budget per channel.

### 11.3 Ordering and addressing

11.3.1 Within a channel, ACTIVE lights are addressed by their position in the
sorted order (§6.4), so consecutive updates need only a **run length** or a
**gap (skip) count**, never absolute indices. Absolute identity is established
once by the session header (§11.7).

### 11.4 Quantization and the per-light wire format

11.4.1 **Internal quantized precision** (the canonical decoded state, per
light): `qL` — **6 bits** over L∈[0,1]; `qC` — **5 bits** over C∈[0,
C_max=0.4]; `qH` — **8 bits** over H∈[0,360), wrapping. All predictor math
operates in these integer units. Quantizing in OKLCH (perceptual) keeps equal
codes ≈ equal perceptual steps.

11.4.2 **Keyframe fields carry the top significant bits**: 5 of qL, 4 of qC,
7 of qH — `[L5|C4|H7]` = 16 bits (2 bytes) per light. Encode rounds
(`field = (q+1)>>1`, clamped; hue wraps); decode reconstructs `q = field << 1`.
A keyframe therefore lands within 1 LSB of full precision; the bottom bit is
recovered by subsequent deltas.

11.4.3 **Delta fields carry signed fine corrections** in sign+magnitude form:
1+4 bits for L, 1+3 for C, 1+6 for H — `[sL|mL4|sC|mC3|sH|mH6]` = 16 bits
(2 bytes) per light. A correction is in LSB units of the full 6/5/8-bit
precision: range ±15 L, ±7 C, ±63 H (H wraps mod 256). Corrections that would
exceed the range **saturate**; a saturated light is corrected further on
following frames (eventual correctness, §11.1.2) or erased by the next
keyframe. Both frame kinds thus cost exactly 2 bytes/light; deltas win by
paying only for the lights that need correcting (§11.6).

11.4.4 The quantized triple (qL,qC,qH) is the *canonical decoded value*: both
encoder and decoder operate on quantized integers, so the encoder's model of the
decoder is exact (no float divergence across languages, §11.5.3).

### 11.5 The shared predictor (`predictor.py`)

11.5.1 Per ACTIVE light, both ends keep a small state: last decoded quantized
value `q=(qL,qC,qH)` and a per-component velocity `v`. The **prediction** for
the next frame is `q_pred = q + v` (component-wise, with hue on the mod-256
ring). This is the "dead reckoning / projective velocity blending" of the brief.

11.5.2 Each transmitted update for a light carries the §11.4.3 signed
**correction** to the predicted value; the decoder sets `q = q_pred +
correction` and blends `v` toward the realized change, giving projective
velocity blending. The exact integer arithmetic is normative in §11.5.4.

11.5.3 **Encoder simulates decoder.** The encoder runs this exact integer
predictor to know what the decoder currently believes, computes each light's
prediction error against the freshly quantized ground truth (available because
rendering is stateless, §1.3.4), and chooses corrections. Because both sides run
identical integer math, they never diverge between keyframes except where the
encoder *chooses* not to correct (bounded, §11.6).

11.5.4 **Normative integer arithmetic** (identical in Python/NumPy, JS, C++;
right shifts are arithmetic/floor; int32 state): velocity `v` is stored in
1/8-LSB fixed point. On every non-keyframe frame, for every ACTIVE light and
each component: `pred = q + ((v + 4) >> 3)`; L and C clamp to [0,63]/[0,31], H
reduces mod 256 (always-positive: `((x mod 256) + 256) mod 256`). If a
correction was transmitted, `q_new = pred + corr` (clamp/wrap), else
`q_new = pred`. Then, with realized step `d = q_new − q_old` (for H the
shortest signed difference in [−128,127]): `v += ((d << 3) − v) >> 2`
(i.e., α = 1/4). A KEYFRAME sets `q` directly and resets `v = 0`.

### 11.6 Adaptivity: error-ranked, budgeted updates

11.6.1 Each frame has a byte **budget** (configurable; for serial it is the
per-tick byte allowance at the chosen baud; for WS it can be large). 11.6.2 The
encoder scores every ACTIVE light by prediction error (a perceptual weighting of
the qL/qC/qH deltas) and emits corrections for the worst-error lights first,
encoding "no-correction" runs compactly, until the budget is spent. 11.6.3
Un-corrected lights coast on `v_pred` (dead reckoning), so smoothly-moving
patterns cost almost nothing; lights left slightly wrong are picked up in later
frames or the next keyframe → eventual correctness (§11.1.2). 11.6.4 This single
mechanism delivers "as few bits as possible" + "adaptive to throughput" +
"eventually correct" without separate modes.

### 11.7 Framing, session header, keyframes

11.7.1 Transport framing: each wire frame is a byte buffer = `[header]
[payload]`, COBS-encoded with a trailing zero delimiter and a CRC16 over the
payload (so the serial reader resynchronizes on corruption). The WS driver sends
the same buffers as binary messages (no extra framing needed, but kept identical
for golden-vector reuse).

11.7.2 Frame types: `SESSION` (once at start / on resync), `KEYFRAME`, `DELTA`
host→device; `HELLO`, `RESYNC`, `ACK` (§11.7.6) device→host.
The `SESSION` frame uploads, per channel: the count and `index` of ACTIVE lights;
and the interpolation map — for each INTERPOLATED light, its bounding ACTIVE
neighbors and weight `w` (u8) (§6.2.3) — and per-controller brightness/color
correction (§8.4.3). After `SESSION`, the firmware/JS knows its entire light map;
subsequent frames carry only colors.

11.7.3 `KEYFRAME` sends every ACTIVE light's full quantized OKLCH (resets
predictor state on both ends). Keyframes are sent on session start, on
pattern/lights change (§10.4), on decoder resync request, and periodically every
`keyframe_interval` ticks (default ≈ every 2–5 s) to bound drift. 11.7.4 `DELTA`
carries the budgeted corrections of §11.6 as `(skip run, [corrections])*`.

11.7.5 Frame header fields: version, type, `controller`, `t` (float64 seconds,
used for logging/sync and to let a late joiner recompute), and payload length.
`t` is authoritative from the server; the firmware does not need a clock for
correctness (it applies frames as they arrive) but may use `t` for diagnostics.

### 11.7.6 Flow control

11.7.6.1 `ACK` (type 5, device→host) acknowledges consumed frames. The
acknowledged frame is identified by its header `t`, echoed in the ACK's own
header `t`; the ACK carries no payload. Acknowledging `t` retires every frame
at or before it, so a dropped ACK is self-correcting — the next one
re-establishes the true position instead of leaving the sender permanently
short. Reusing `t` as the sequence key keeps the header at 13 bytes and the
golden vectors (§11.9) untouched, since those cover host→device frames only.

11.7.6.2 The device emits at most one ACK per loop iteration, and only when
its consumed-frame count has changed, so an idle device is silent and a busy
one self-limits to its true service rate. A frame that was consumed but could
not be applied — an oversized `SESSION` (§13.7) — is still acknowledged: it
occupied the input buffer, and withholding the ACK would stall the sender
with no way to recover.

11.7.6.3 The sender maintains at most `max_in_flight` unacknowledged frames
per controller (default 4, ≈130 ms of added latency at 30 fps). When the
window is full it **skips the tick entirely** rather than rendering and
discarding: the encoder models the decoder's state (§11.8.1), so advancing it
without transmitting would desync every subsequent `DELTA`. Skipping leaves
both ends on the last applied frame and the next `DELTA` follows correctly
from there, needing no keyframe.

11.7.6.4 A controller that has never sent an ACK is exempt from the window,
so firmware predating this section degrades to unpaced streaming rather than
deadlocking after `max_in_flight` frames. A non-monotonic `t` (pattern loop or
seek, §10.4) clears that controller's outstanding entries, since no later ACK
could ever retire them.

11.7.6.5 Rationale: the RP2040's USB-CDC stack does not apply backpressure
when its receive buffer backs up — it stops responding to the host entirely,
and recovery requires physically reconnecting the device. Flow control is
therefore a correctness requirement of the transport, not a throughput
optimization. Measured on a Feather SCORPIO: ~117 KiB/s of framing the device
discards without decoding, ~69 KiB/s decoded and rendered for a 104-active-light
geometry, and an unrecoverable stall after roughly 4 s of sustained overdrive.

11.7.6.6 The window doubles as the feedback for budget adaptation. The §11.6.1
baud math answers what the *link* can carry, but the binding limit is what the
*device* can decode and repaint at frame rate, which varies by geometry and
hardware. When the sender fills its budget from the link rate alone (a
`SerialDriver` whose caller did not set `budget_bytes`), it instead starts
small and adapts on two overload signals: a skipped tick (window full,
§11.7.6.3), and a median ACK round trip exceeding the frame interval. The
second signal is essential, not redundant — when serial writes block on a
backed-up OS buffer, ACKs arrive during the blocked write and the window
never fills, so frame rate sinks with no stall ever recorded; the round trip
measures device service time directly and cannot be masked that way. Either
signal shrinks the budget multiplicatively; sustained clean operation with
round trips comfortably inside the interval grows it additively back toward
the §11.6.1 ceiling. DELTA frames are self-describing, so the
budget may move mid-session without decoders noticing (§11.8.2's "the server
tunes only budget/cadence" is understood to include tuning *within* a
session). An explicitly configured budget is never adapted.

### 11.8 Codec API

11.8.1 `Encoder(lights, config)` → `.session_frame()`, `.keyframe(oklch)`,
`.encode(oklch, t) -> bytes` (emits KEYFRAME when due else DELTA), and
`.request_resync()`. `Decoder(session)` → `.decode(bytes) -> DecodeResult` where
`DecodeResult` exposes the per-light quantized OKLCH and a dirty mask. The Python
`Decoder` is the **reference** (§1.3.7) used by the encoder's self-simulation,
by tests, and to generate golden vectors.

11.8.2 `CodecConfig` holds keyframe interval, budget policy, brightness/color
correction, and version. The quantization widths and predictor constants of
§11.4/§11.5.4 are fixed by this spec (review §19.2) and live as constants in
`protocol.py`; the server tunes only budget/cadence per session (e.g. larger
budget for WS).

### 11.9 Conformance and golden vectors

11.9.1 `firmware/golden/` holds, checked-in: a fixed lights geometry, a fixed
pattern trace, and the exact byte frames the reference encoder emits, plus the
expected decoded OKLCH per frame. 11.9.2 The Python, JavaScript, and C++ decoders
each have a test that replays the golden frames and asserts bit-exact decoded
output. This is how three implementations stay faithful to one spec (§1.3.7) and
how we prevent the demo and production decoders from drifting apart.

### 11.10 Bandwidth sketch (sanity, not a guarantee)

11.10.1 Baseline (keyframe-every-frame: every ACTIVE light at 2 bytes/light,
§11.4.2) at 8 channels × 256 lights × 30 fps ≈ 123 KB/s ≈ 1.0 Mbit/s — fine
over USB CDC. 11.10.2 Delta operation on a typical smooth pattern is expected
to drop average cost by 5–20× (few corrections per frame + dead-reckoning
coasting); this is a *target* to be measured, and the budget mechanism
guarantees we never exceed the link regardless.

---

## 12. Drivers

### 12.1 Role

12.1.1 A driver moves `engine.frames()` bytes onto a transport and, where the
transport is bidirectional, relays decoder control messages (resync requests)
back to the engine. Drivers contain no color/codec logic.

### 12.2 Serial driver (`drivers/serial_driver.py`)

12.2.1 Opens the Scorpio's USB-CDC serial port (`pyserial`), performs the
handshake (§13.3), sends `SESSION` then paces `DELTA`/`KEYFRAME` frames at the
tick clock, computing the per-tick byte budget from the negotiated baud
(§11.6.1). 12.2.2 Reads inbound bytes for resync requests / handshake / logs and
forwards resyncs to the engine. 12.2.3 Handles reconnect (port drop → reopen →
re-handshake → keyframe). 12.2.4 Multi-controller topology (decided, review §19.7): **one process, one
engine, several ports.** The engine renders the whole lights array once per
frame (one vectorized pattern evaluation, one clock) and its encoder emits one
frame per controller; the serial driver opens one port per controller and
routes each frame by its header's controller id. Per-consumer predictor
sessions (§12.4) make this safe. One-process-per-controller is rejected: it
would duplicate pattern evaluation and desynchronize clocks.

### 12.3 WebSocket driver (`drivers/websocket_driver.py`)

12.3.1 For each connected browser, sends the same `SESSION` frame then streams
the same `DELTA`/`KEYFRAME` binary buffers the serial path uses. 12.3.2 New
client → its own keyframe (cheap, stateless engine). 12.3.3 Receives resync
requests over the socket. 12.3.4 This driver is the live half of the web API's
`/api/play` endpoint (§15.4).

### 12.4 Multi-consumer note

12.4.1 Because frames are pure bytes derived from `t`, one engine can feed serial
and WebSocket simultaneously (the demo mirrors the installation). Per-consumer
predictor state differs only if budgets differ; the encoder keeps one predictor
per *transport session* (a thin wrapper holding per-session state around the
shared predictor), not one global predictor — this is the one subtlety to
implement carefully and is covered by tests.

---

## 13. Scorpio Firmware (client decoder + graphics)

### 13.1 Platform

13.1.1 Target: **Adafruit Feather RP2040 SCORPIO** (8 level-shifted parallel
outputs). Language: **Arduino C++** using **Adafruit_NeoPXL8** for the eight
parallel strips. Per review (§19.4) this choice is driven purely by
performance: CircuitPython cannot sustain decode + color conversion +
interpolation for thousands of LEDs at 30 fps on the RP2040; C++ with
fixed-point/LUTs can, with headroom. If bring-up measurements ever show
otherwise the decision can be revisited, but C++ is the safe default and the
decoder core is plain C++ (host-testable) either way.

### 13.2 Responsibilities

13.2.1 Read framed bytes from USB serial; 13.2.2 decode `SESSION`/`KEYFRAME`/
`DELTA` using the spec decoder (§11), maintaining per-channel quantized OKLCH +
velocity state; 13.2.3 reconstruct INTERPOLATED lights (§13.5); 13.2.4 convert
all lit lights OKLCH→OKLab→linear sRGB→gamma sRGB8 with brightness/color
correction (§8.4); 13.2.5 write into NeoPXL8 buffers indexed by
`(channel,index)`; 13.2.6 `show()` double-buffered; 13.2.7 emit resync on CRC
failure or buffer underrun.

### 13.3 Handshake

13.3.1 On boot the firmware sends a `HELLO` reporting firmware version,
controller id, channel count (8), max lights/channel, and supported codec
version. The driver replies with the negotiated `CodecConfig` and `SESSION`.
13.3.2 If the firmware sees a frame for an unknown session (e.g. server
restarted), it requests resync.

### 13.4 Fixed-point color path

13.4.1 The OKLab→RGB cube and the sRGB gamma are implemented with integer/
fixed-point math and small 1-D lookup tables (a cube/`x^3` table on `l_,m_,s_`
and a gamma table on linear→sRGB8), precomputed at boot. The matrices are the
§8.4 constants in fixed-point. 13.4.2 Golden-vector tests (§11.9) plus a color
round-trip tolerance test guard this approximation against the float reference.

### 13.5 Interpolation on device

13.5.1 From the `SESSION` map, each INTERPOLATED light knows its two bounding
ACTIVE neighbors on the channel and weight `w`. The firmware fills each
INTERPOLATED light in OKLCH with shortest-arc hue (§8.2.2): `L = (1−w)·L_prev +
w·L_next`, likewise C, and `H = H_prev + w·Δ` where `Δ` is the shortest signed
hue difference (mod-256 in quantized units) — then converts OKLCH→OKLab→RGB
like any other light. INACTIVE lights are written black/off. 13.5.2
Interpolation is the firmware's main per-light loop; it is written
branch-light and, if needed, the candidate for SIMD/PIO later.

### 13.6 Build/flash

13.6.1 `firmware/scorpio/` is a self-contained Arduino/PlatformIO project with a
README for board setup, NeoPXL8 pin mapping, and flashing. A "Scorpio board
image exists to accept wire serial input" (exit condition) = this project built
and flashable, with a loopback test mode that drives a known pattern from a
canned `SESSION`+frames for bring-up without a server.

---

## 14. Web Client

### 14.1 Role

14.1.1 Two distinct views, sharing one projection (§14.4): a **geometry
preview** (render a scaffold and/or a lights geometry statically) and a **live
playback** (decode the wire protocol and animate). The live view is the protocol
test (§1.3.2).

### 14.2 Decoder in JS

14.2.1 `static/decoder.js` implements the §11 decoder (SESSION/KEYFRAME/DELTA,
predictor, dequantization) — a conformant sibling of the Python/C++ decoders,
verified by golden vectors (§11.9). It outputs per-light quantized OKLCH;
interpolation (§13.5, OKLCH shortest-arc) is done in JS identically to
firmware; `static/color.js` then does OKLCH→OKLab→sRGB8 (the §8.4 math).

### 14.3 Live rendering (Canvas)

14.3.1 Live playback renders to a **Canvas 2D** (not per-element SVG): the
client first fetches the **layout** for its lights geometry over REST
(`GET /api/lights/{id}/layout` — positions, kinds, weights, display shapes
(§6.5.3), viewBox) and builds a per-light draw list once; the WebSocket then
carries *only* wire bytes, identical to serial. Each frame: decode bytes →
colors → repaint. Lights with a display shape are drawn as that polygon (beams,
per review §19.5); others as dots. Canvas is required for thousands of lights
at 30 fps; per-frame SVG DOM mutation (the 2.0 approach) does not scale and is
dropped for playback.

14.3.2 The client connects to `/api/play?lights=<id>&pattern=<name>` (§15.4),
which sends binary wire frames. The client may send resync (e.g. on tab
re-focus) over the same socket.

### 14.4 Shared projection (`render/projection.py` + mirror constants)

14.4.1 The mapping from world coordinates to 2D screen geometry (which space,
which projection, scale, viewBox) is computed once server-side and delivered to
the client (in the SESSION/preview payload), so the SVG static renderer and the
Canvas live renderer place lights identically. There is one projection rule, not
two (§1.3.1).

### 14.5 Static preview (SVG)

14.5.1 Static geometry/preview pages use the server-side SVG renderer
(`render/svg.py`, reusing the 2.0 SVG primitive emitters and, for pentagon
inputs, the beam-polygon diagram). Static colored previews at a given `t` use
`engine.colors_srgb8(t)` (§10.5). SVG is fine here because it is rendered once,
not per frame.

### 14.6 UI

14.6.1 Minimal but complete: geometry chooser, pattern chooser (from
`/api/patterns`), play/pause, FPS + bytes/s + bytes/light readout (so the
operator can see the codec working), connection status, and a "force keyframe /
resync" button for testing.

---

## 15. Web Server API

### 15.1 Role and boundary

15.1.1 `server/app.py` (FastAPI) is a thin adapter exposing the exit-condition
API over the engine, drivers, and store. It holds no rendering or codec logic;
it translates HTTP/WS ↔ engine calls. The engine never imports it (§2.2.2).

### 15.2 Resource model

15.2.1 Resources: **scaffolds**, **lights**, **patterns**. Scaffolds and lights
are JSON documents addressed by an `id` (a content hash or a user-supplied
slug); patterns are uploaded Python files registered by `name` (§15.5).

### 15.3 REST endpoints (maps 1:1 to exit conditions)

15.3.1 Geometry in/out and rendering:

| Method & path | Purpose (exit condition) |
|---|---|
| `POST /api/scaffolds` | Save a scaffold geometry → `{id}` |
| `GET /api/scaffolds` | List available scaffolds |
| `GET /api/scaffolds/{id}` | Fetch scaffold JSON |
| `GET /api/scaffolds/{id}/view` | HTML page rendering the scaffold (§14.5) |
| `POST /api/lights` | Save a lights geometry → `{id}` |
| `GET /api/lights` | List available lights geometries |
| `GET /api/lights/{id}` | Fetch lights JSON |
| `GET /api/lights/{id}/view` | HTML page rendering the lights geometry |
| `GET /api/lights/{id}/layout` | Client draw layout: positions, kinds, weights, display shapes, viewBox (§14.3.1) |
| `POST /api/lights/from-scaffold` | Produce a lights geometry from `{scaffold_id, params}` using default capture (§7.2) → `{id}` |
| `POST /api/patterns` | Upload a pattern file; hot-reload registry (§9.3) → `{name}` |
| `GET /api/patterns` | List available patterns (name, description, load status) |
| `GET /api/health` | Liveness + engine/codec versions |

15.3.2 `GET .../view` returns HTML that loads the static client in the
appropriate mode and the referenced geometry. Listing endpoints return metadata
(id, name, counts), not full documents.

### 15.4 Play WebSocket

15.4.1 `WS /api/play?lights=<id>&pattern=<name>[&fps=..&budget=..]`: the server
builds (or reuses) an `Engine` for that lights+pattern, attaches the WebSocket
driver (§12.3), sends `SESSION`, then streams wire frames at `fps`. Inbound
messages: `resync`, `set_pattern` (hot-swap, §9.3.2), `pause/resume`. This is the
"connect to a play-pattern websocket that streams a selected pattern to the
webclient using the wire comms protocol" exit condition, and it uses the exact
production codec.

### 15.5 Pattern upload & hot-reload

15.5.1 `POST /api/patterns` accepts a `.py` file, writes it to the uploads
patterns dir, calls `registry.reload()`, and returns the discovered pattern name
or a structured load error (never crashes the server). 15.5.2 `GET /api/patterns`
reflects the live registry, including any file added on disk out-of-band, on next
reload. Security note: uploaded patterns execute arbitrary Python in-process;
2.1 assumes a trusted operator on a LAN and documents this; sandboxing is out of
scope.

### 15.6 Store (`server/store.py`)

15.6.1 A filesystem-backed store: scaffolds in `store/scaffolds/<id>.scaffold.json`,
lights in `store/lights/<id>.lights.json`, patterns in `patterns/uploads/`.
`id` defaults to a short content hash so identical saves dedupe; a `name` may
alias an id. No database — simple, inspectable, git-friendly. The store is the
only stateful server component and is trivially swappable behind its small
interface.

---

## 16. Command-Line Interface

### 16.1 Principle

16.1.1 The CLI is another adapter over the same engine and drivers — every CLI
verb maps to engine + a driver/renderer, so the CLI exercises the production path
too (§1.3.2). No CLI verb contains rendering/codec logic of its own.

### 16.2 Verbs

16.2.1 `luminary serve [--host --port]` — run the web server (§15).
16.2.2 `luminary play --lights <file|id> --pattern <name> --serial <port>
[--baud --fps --budget]` — stream to hardware via the serial driver (the brief's
"core engine run with a driver for wire serial output"). `--ws` instead streams
headless over WebSocket for a manual browser; omitting both prints codec stats
(a dry-run that still runs encode, for profiling).
16.2.3 `luminary capture --scaffold <file> [--params <file>] -o <out.lights.json>`
— default capture (§7.2).
16.2.4 `luminary render --lights <file|id> --pattern <name> -t <seconds> -o
out.svg` — static SVG via §10.5/§14.5 (supersedes 2.0 `pattern sample`).
16.2.5 Kept utilities: `luminary svg`, `luminary index`, `luminary validate`
(2.0 behaviors, now over the refactored renderers).

---

## 17. Testing, Tooling, and Performance

### 17.1 Tooling (unchanged house rules)

17.1.1 `black` formatting, `mypy --explicit-package-bases` typing, and `pytest`
remain mandatory (per `plan/guidelines/code-quality.md`). New numeric modules
carry type hints and shape comments.

### 17.2 Test layers

17.2.1 **Unit**: coords conversions (round-trip), color conversions (round-trip +
known-value vs reference), capture determinism, schema validation, predictor
math. 17.2.2 **Golden vectors**: the codec conformance corpus (§11.9), run
against the Python decoder in CI and against JS/C++ decoders where those toolchains
are available. 17.2.3 **Integration**: engine `frame(t)` → decode → compare
decoded OKLCH within quantization tolerance of `pattern.render`; full
encode→decode→interpolate→sRGB pipeline on a sample geometry. 17.2.4 **Property**:
"eventual correctness" — after a bounded number of frames without motion, decoded
state converges to ground truth; keyframes reset drift to zero. 17.2.5 **Firmware**:
host-compiled C++ unit tests for the decoder + fixed-point color against golden
vectors; on-device loopback bring-up (§13.6).

### 17.3 Performance budgets (targets to measure, not vibes)

17.3.1 Pattern eval + encode for 8×256 lights: ≤ 5 ms/frame on a Raspberry-Pi-class
server (≪ 33 ms tick). 17.3.2 Color conversion (vectorized) for the same: ≤ 2 ms.
17.3.3 Firmware decode+convert+show at 30 fps for the target light count without
underrun. 17.3.4 Each is asserted by a benchmark test with headroom alarms;
failing a budget is a release blocker for 2.1.

### 17.4 Hot-reload safety

17.4.1 Tests that a broken uploaded pattern is reported, not fatal (§9.3.1), and
that reload swaps implementation without dropping the serial session.

---

## 18. Build Phases / Milestones

> Ordered so each phase ends with a working, demonstrable, production-faithful
> slice. Branch naming follows `plan/guidelines/version-control.md`
> (`foundation/<feature>/_`, ending `/_`).

18.1 **Phase 0 — Spine.** Repo restructure (§2.2); `color/convert.py` (§8) with
tests; `geometry/coords.py` (§4); `LightColumns` + `LightsGeometry` load/save
(§6) with a hand-authored sample lights file. *Demo:* load a lights file, print
the array, convert to sRGB, round-trip.

18.2 **Phase 1 — Geometry in/out + static preview.** `scaffold.py` (§5);
`render/projection.py` + `render/svg.py` (§14.4–14.5); pentagon→scaffold/lights
adapters (§5.5, §7.3); server skeleton with scaffold/lights save/list/get/view
(§15.3). *Demo:* upload/inspect a scaffold and a lights geometry in the browser.

18.3 **Phase 2 — Patterns + codec + WS demo.** `Pattern` contract + registry
(§9); port example patterns (§3.5); engine `frame(t)` (§10); the **full codec**
(§11: SESSION/KEYFRAME/DELTA, predictor, budgets); WebSocket driver + Canvas
client + JS decoder (§12.3, §14). *Demo:* pick a pattern in the browser, watch
it animate via the real wire codec; bytes/s readout live.

18.4 **Phase 3 — Serial + Scorpio firmware.** `serial_driver.py` (§12.2);
`firmware/scorpio/` decoder + fixed-point color + interpolation + NeoPXL8 (§13);
golden vectors (§11.9) + firmware conformance tests. *Demo:* the same pattern
runs on physical LEDs from the same engine — production path live.

18.5 **Phase 4 — Capture + from-scaffold API.** `capture/from_scaffold.py` (§7.2)
with interpolation policy; `POST /api/lights/from-scaffold` (§15.3);
`from_scan` interface stub + bundle format (§7.4). *Demo:* generate a lights
geometry from a scaffold with defaults and immediately play it.

18.6 **Phase 5 — Codec tuning & measurement.** With the format fixed (§11.4),
this phase is empirical: measure bytes/light across the pattern corpus, tune
budget policy, keyframe cadence, and error weights; stress the budget cap;
freeze golden vectors v1 (§11.9). *Demo:* bytes/light drops sharply on smooth
patterns with identical visuals; budget cap holds under stress.

18.7 **Phase 6 — Hot-reload + polish.** Pattern upload + reload (§15.5); listing
completeness; multi-controller serial (§12.2.4); validation/docs; performance
gate (§17.3). *Demo:* upload a new pattern file and play it without restart, on
both web and hardware.

---

## 19. Review Resolutions (2026-07-09)

> All ten open questions were resolved in review; the body of this spec has
> been updated to match. Recorded here for the audit trail.

19.1 **Timestep is a float.** `t` is elapsed seconds as a float, not an integer
tick (§1.3.4, §9.1). Frame counters are internal to the engine/codec only.

19.2 **Quantization widths fixed by review** (§11.4): internal precision
6/5/8 bits (L/C/H); keyframes carry the top 5/4/7 bits; deltas carry
sign+magnitude 1+4 / 1+3 / 1+6 corrections. Both frame kinds are 2 bytes/light.

19.3 **Interpolation is OKLCH with shortest-arc hue** (§8.2.2, §13.5), not
OKLab.

19.4 **Firmware: C++/NeoPXL8**, chosen on performance grounds; the original
recommendation is a year old but performance is what matters and C++ is the
safe default. Decoder core stays plain host-testable C++ so the call can be
revisited with measurements (§13.1).

19.5 **Beams are not a core-engine concept.** They are retained in the
geometry-based (pentagon) constructor and in the web frontend's rendering, via
per-light `display` shapes (§6.5.3, §7.3.1, §14.3.1).

19.6 **Pentagon identity mapping deferred.** Round-robin default documented in
one place until physical strip routing is known (§7.3.1).

19.7 **Multi-controller: one process, one engine, several ports** (§12.2.4) —
single vectorized render and a single clock; frames route by controller id.

19.8 **XY projection goes first.** The planar path is the priority for capture,
preview, and the first installation; XYZ/spherical support ships but is
exercised second (§4.1, §18).

19.9 **Camera scan stays an interface-only stub in 2.1** (§7.4).

19.10 **Pattern upload trust model confirmed**: trusted operator on a LAN;
uploaded patterns execute in-process; sandboxing out of scope for 2.1
(§15.5.2).
