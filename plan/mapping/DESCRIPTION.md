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

## Mirror mode

Before and during mapping, the base station shows a live window of
exactly what is being driven: the engine's frames go to the serial
ports *and* to a local browser page over WS — the single-engine
broadcast of spec §12.4 (designed, previously unwired). Same wire
bytes, decoded by the existing browser decoder. No second render path.

## The sequence

One state machine, surface-agnostic (see below). Keys: arrow keys and
WASD are equivalent; enter confirms.

**Stage A — ports to boards.** For each planned data unit, the window
breathes one color on that unit's planned panel region; the wire sends
the same breathing to *all channels* of one candidate board. ←/→ moves
the breathing to a different board (by controller id) until the
physical cluster that lights up matches the window; enter locks the
assignment. Confirmed boards keep breathing at half brightness while
the rest are mapped.

**Stage B — panels, winding, density (per board).** The window breathes
one planned panel; ←/→ changes which channel carries the signal until
the right physical panel breathes. Then the panel switches to the
orientation test: a sixth of a color wheel centered on the panel's
six-red corner, with a dark band sweeping clockwise around that vertex.
↑ toggles density (180/360 — wrong density shows as the wheel occupying
the wrong arc), ↓ toggles winding (wrong winding shows the band
sweeping the wrong way). A **single enter** confirms channel + density
+ winding together and advances; the confirmed panel holds its test
pattern at half brightness until the board completes.

**Stage C — mapped boards.** A fully mapped board flips to the "mapped"
pattern: a horizontal ring of light, hue varying around the
circumference, descending from the apex at constant angular-elevation
velocity every few seconds (`PHI_S` is filled by the fold — PR #13),
layered over the beads backdrop. Unmapped panels play *only* beads.

**Beads backdrop.** Gentle white beads that grow, fade, and drift a
short way along a strip straightaway, with a mirrored twin on the far
side of the same strut — the twins only visually align once mapping is
correct, which makes drift or error visible at a glance. Beads is also
the firmware's default idle pattern before a host connects (see board
storage below), so an unmapped, unhosted board looks intentional.

## Saved state

One YAML per board, keyed by controller id — draft schema:

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
  without hardware.

Entry point: one script (`python -m luminary.cli map`, flags
`--continue`, `--trust-boards`) — details at implementation time.

## Identity mapping (closes spec §19.6)

The mapping parametrizes capture. Once a board's YAML exists, the
pentagon capture assigns identity per panel from it: channel from the
mapping, strip index 0 at the six-red corner, indices advancing in the
recorded winding, 180 or 360 lights per the recorded density (the
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
