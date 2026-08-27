# Physical mapping — design

Deployment must connect the *plan* (which panel sits on which dome face,
which data unit serves it — `configs/sphere3v.json`) to the *build*
(whatever actually got plugged in). Four facts per panel are unknown
until someone stands in front of the sphere:

| Unknown | Resolved by |
|---|---|
| Which USB port carries which board | auto-probe + Stage A confirmation |
| Which channel (0–7) drives which panel | Stage B, interactive |
| Strip winding: CW or CCW | Stage B, interactive |
| LED density: 180 or 360 per panel | Stage B, interactive |

Two facts are **settled** and the tooling relies on them:

- **Density is mixed per panel with no organization** — panels of both
  densities were plugged wherever; density is discovered and recorded
  per panel at mapping time, never assumed.
- **The strip's start corner is always the panel's six-red-struts
  vertex** (the hexagon-center corner). Every plan-A face is B-C-C, so
  this corner is derivable: the vertex where the face's two C (red)
  struts meet. Orientation per panel is therefore exactly one bit
  (winding), anchored at a known corner — and strip index 0 is at that
  corner by construction.

Boards self-identify: `firmware/tools/whoami.py` provokes a RESYNC,
which carries the compiled-in controller id, so port ↔ controller-id is
probed automatically and mappings are keyed on **controller id**, never
port paths — replugging USB later cannot scramble a saved mapping.

**Production plan (this year): 4A-33 with data-aux.** The net is 4A-33
(33 panels) and the data wiring uses the construction app's aux mode
"data" (`sphere3v.json` `electronics.data_aux`): the front hexagon unit
(vertex 8, over the door) keeps its power role but fields no data
board — its three hairband panels ride the flanking hexes over chained
secondaries, two on the screen-right hex (unit 9, board 2 in plan
order: faces 3·4·8 and 4·8·14) and one on the left hex (unit 7, face
3·8·13). Six boards cover all 33 panels; the reassigned panels' strip
start corner stays vertex 8 (physical), only their serving board moves.
`Plan.load()` defaults to this; `data_aux=False` recovers the
seven-board corner-rule plan.

## Mirror mode

Before and during mapping, the base station shows a live window of
exactly what is being driven: the engine's frames go to the serial
ports *and* to a local browser page over WS — the single-engine
broadcast of spec §12.4 (designed, previously unwired). Same wire
bytes, decoded by the existing browser decoder. No second render path.

## The sequence

One state machine, surface-agnostic (see below). Keys: arrow keys and
WASD are equivalent; enter, `p`, and space all confirm — so the whole
flow works on an alpha-only keyboard with no special keys.

The window and the wire are an **exact broadcast of one scene**, held
two ways. First, every board has one role at a time (beads / breathe /
solid / active test / ring), applied to its planned panels on the
window and to its strips on the wire; only placement differs (recorded
strips use their recorded density and winding, everything else the
canonical hypothesis: channel j ↔ planned panel j, 360 LEDs, ccw).
Second — and structurally — every rendered light carries a **reference
net light**: all positional fields (beads, board hues, the wheel, the
ring, the finale, even the post-mapping show) are evaluated *only* on
the net capture and gathered through that reference, so there is no
wire-side field evaluation that could diverge; the hypothesis changes
which net lights a strip's indices reference, never the field values.
The demo mockup paints decoded strips through the same references.
Every probed controller is on the wire in every stage, so nothing
physically plugged ever strands its last frame — before mapping,
boards carry the beads backdrop, landing scrambled on the build by
construction.

**The strip path (physical, and the hypothesis).** A panel's strip
starts at its six-red corner, runs half-way down the first edge, in
along that radial to the center and back out its other side, finishes
the edge; then the same on the far edge and on the third, returning to
the start corner — twelve legs, matching the capture's beam runs
(`[19, 11, 11, 19]` per facet). Hypothesis LED i of n sits at
arclength (i + 0.5)/n along this path; a cw winding walks the same
path the other way. This is the serpentine spec §19.6 was waiting on;
identity capture should assign indices along it.

Each board also owns an **identity color**: pleasant OKLCH hues spaced
equally around the color wheel in plan order (moderate chroma — tags,
not tests).

**Stage A — ports to boards.** The board being placed breathes its
identity color — on the window over its planned panel region, on the
wire over *all channels* of one candidate controller. ←/→ moves the
breathing to a different controller until the physical cluster that
lights up matches the window; enter locks the assignment. A locked
board switches to holding its color **steady** (no more breathing); a
deselected candidate falls back to beads.

**Stage B — panels, winding, density (per board).** The strip under
test plays the orientation test: hue is the light's angle about its
**board's vertex** — one continuous wheel per board, fixed by logical
position (recording mappings never moves it); aux and consolidated
panels continue their board's wheel rather than starting their own
about their physical corner — under a three-spoke dark windmill
sweeping slowly clockwise around that vertex (three spokes = a third
of the wait per panel). The active strip lights only its **first and
last index quarters**, deliberately dark between, so a density
mismatch in either direction reads as "only one half lit" rather than
a subtle hue shift. ←/→ changes which channel carries the test until
the right physical panel lights; ↑ toggles density (180/360),
↓ toggles winding (wrong winding shows the windmill sweeping the wrong
way). A **single enter** confirms channel + density + winding together
and advances; a confirmed panel holds its wheel portion at 20% of the
active strip's brightness until the board completes. Meanwhile every
*unmapped* strip on the active board lights its **first 30 LEDs** with
its intended wheel portion at the same 20% (the flock of corner glows
shows at a glance which physical panels belong to this board), and
boards waiting their turn hold their steady identity color.

**Stage C — mapped boards.** A fully mapped board flips to the "mapped"
pattern *on both surfaces*: a horizontal ring of light, hue varying
around the circumference, descending from the apex at constant
angular-elevation velocity every few seconds (`PHI_S` — filled by the
fold on the window, borrowed from the nearest net light per hypothesis
strip on the wire), each successive wave spinning its hues by a seeded
random angle, layered over the beads backdrop.

**Finale.** The moment the last panel is recorded, both surfaces play
the completion sequence: **three rainbow waves in quick succession**
(1.8 s each) over the still-running beads backdrop — **the last wave
sweeps the beads out behind its front** — a **beat of black**, then the
**`spiral` pattern wipes in through phi, apex to rim, behind a
soft-bordered edge** — after which the show simply plays. The finale is
anchored to the completion moment on the session clock (a construction
parameter of the swapped-in pattern instance, so patterns stay pure);
a session resumed directly into the done stage replays it once from its
own start.

**Beads backdrop.** White beads that fade in, crawl the length of a
strut (either direction), and fade out, all within about two seconds —
independent seeded phases per strut and lane, staggered rather than
synchronized — with a mirrored twin on the far side of the same strut:
the twins only visually align once mapping is correct, which makes
drift or error visible at a glance. Beads is also the firmware's
default idle pattern before a host connects (see board storage below),
so an unmapped, unhosted board looks intentional.

## Saved state

One YAML per board, keyed by controller id, in the runtime state tree
(`var/mapping/` by default; the tutorial's session uses
`var/mapping-demo/`). **The store is the only place mapping state may
live** — every surface, the hardware-free tutorial included, persists
through the same `MappingStore` code; there is no memory-only or
alternative path (the tutorial resumes from its store like
`--continue`, and its ↺ restart control clears the records the same
way they were written). Draft schema:

```yaml
schema: luminary.mapping/1
board:
  controller_id: 3          # compiled-in; probed via RESYNC
  data_unit_vertex: 9       # sphere3v vertex id (the plan)
  port_hint: /dev/ttyACM2   # informational only; reprobed at startup
channels:
  0:
    face: [22, 25, 34]      # sphere3v plan-A face
    winding: ccw            # from the six-red corner, seen from outside
    density: 360            # 180 | 360
  # channels without a mapped panel are simply absent
progress:
  stage: panels             # ports | panels | done
  cursor: 3                 # next channel (or board) to map
```

Write discipline, every step: write → fsync → read back and compare →
copy to `<name>.bak` → fsync. The `progress` block is the `--continue`
marker; it is removed when the board completes, and a run started with
`--continue` resumes from the first board/channel still carrying one.

`--trust-boards`: instead of local files, download each board's stored
mapping, **copy it over the local file** after saving the prior local
copy as a dated backup (`mapping-3.yaml.2026-08-27T0412Z.bak`), then
proceed. This is the base-computer-swap path: the sphere itself carries
its own mapping.

## Surface-agnostic core

The sequence logic is one pure state machine: `(state, input_event) ->
(state, wire_intent, window_intent)`. Two thin adapters drive it:

- **TUI**: raw keypresses from the terminal on the base station; status
  line per step. The window is the mirror page in a browser.
- **Web**: the demo/tutorial page — a mockup sphere with a deliberately
  scrambled physical mapping (including mixed densities) above, the
  preview window below, a start button, on-screen arrow/enter controls,
  and the same keyboard handling. It runs the identical state machine
  against a simulated build, for training and for developing the tool
  without hardware. The main pattern server mounts this tutorial at
  `/demo/mapping` (`luminary.cli serve`; every page/API URL is
  page-relative, so the same app serves standalone or under the
  prefix). All viewers mirror the one live session; its records
  persist in `var/mapping-demo/` through the production store code
  and resume across restarts, and the page's ↺ restart control clears
  them to start the sequence over.

Entry point: one script (`python -m luminary.cli map`, flags
`--continue`, `--trust-boards`) — details at implementation time.

## Identity mapping (closes spec §19.6)

The mapping parametrizes capture. Once a board's YAML exists, the
pentagon capture assigns identity per panel from it: channel from the
mapping, strip index 0 at the six-red corner, indices advancing along
the serpentine strip path above in the recorded winding, 180 or 360
lights per the recorded density (the
`kinds`/`weights` machinery carries 360-LED panels as ACTIVE +
INTERPOLATED if we choose to keep wire cost at 180/panel — decision at
implementation time, measured, not assumed).

## Board-side mapping storage — HANDOFF to prod-hardware integration

The base station's YAML is authoritative during mapping; a copy also
lives **on each board**, for two reasons: base-computer swaps
(`--trust-boards` above), and standalone idle — the beads pattern needs
per-channel length, density, and winding to look right with no host
attached.

Proposed design (plausible for the Feather RP2040 SCORPIO; the marked
items need verification on real hardware by whoever owns the firmware):

1. **Filesystem**: a LittleFS partition on the SCORPIO's 8 MB flash via
   the arduino-pico core (`board_build.filesystem_size` in
   `platformio.ini`; 64–256 KB is ample — mappings are ≤ 4 KB).
   LittleFS survives sketch re-uploads when the filesystem geometry
   stays constant. **Verify:** the pinned core version's LittleFS
   support, and that our upload path (`pio run -t upload`) preserves
   the partition with our chosen geometry.
2. **Files**: `/mapping.yaml` — the host's YAML, stored as an *opaque
   blob* (the firmware never parses YAML); `/mapping.bin` — a small
   fixed-layout mirror the firmware parses at boot for standalone
   beads: magic + version, then per channel `{length u16, density u8,
   winding u1}`, CRC16 (same CRC as the wire) over the lot. The host
   writes both in one transaction; `.bin` is derived, `.yaml` is
   truth.
3. **Transport**: new host↔device frame types over the existing serial
   protocol — `FILE_WRITE` (file id, offset, chunk, final flag) and
   `FILE_READ` (file id, offset) with device `FILE_DATA`/`FILE_ACK`
   responses — riding the existing COBS + CRC16 framing and the ACK
   flow-control machinery from PR #10. This is a protocol change:
   follow the conformance workflow (spec first, frame-type registry,
   `PROTOCOL_VERSION` considerations). The LED decode path and golden
   vectors are untouched — file frames never carry light state.
   **Verify:** CDC throughput and ACK window sizing for ~4 KB
   transfers.
4. **The real hardware gotcha**: RP2040 flash writes stall XIP — code
   executing from flash halts during program/erase. The firmware must
   **pause LED output (NeoPXL8 DMA) and quiesce the second core**
   around the LittleFS commit window, then resume and force a keyframe.
   Do writes only between frames; never mid-show except during mapping.
   **Verify:** NeoPXL8/DMA interaction with flash writes on core1.
5. **Rejected by default** (owner may override): USB mass-storage
   (TinyUSB composite CDC+MSC) — a second USB function on seven boards
   is operationally messy and MSC wants FAT, not LittleFS;
   CircuitPython-style UF2/FAT storage — not the production firmware.

Failure containment: a corrupt or absent `/mapping.bin` (bad CRC, wrong
magic) must degrade to the firmware's built-in default (all channels
180 LEDs, CW) and report the condition in its HELLO — never brick the
idle pattern.
