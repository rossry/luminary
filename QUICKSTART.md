# Quickstart — production deployment

Base station: Linux, Python 3.12. Boards: Adafruit Feather RP2040 SCORPIO,
one per controller id.

Run every command from the repo root. `python` means your virtualenv's.

## 1. Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
sudo usermod -aG dialout $USER      # then log out and back in
```

The group change is not optional — without it every board reads as
"blocked" and nothing can open a port.

Boards get a new device node each time they are flashed. To avoid
re-granting access every time, install
`/etc/udev/rules.d/60-luminary-scorpio.rules`:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="239a", ATTRS{idProduct}=="8121", MODE="0660", GROUP="dialout", TAG+="uaccess"
SUBSYSTEM=="block", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0003", MODE="0660", GROUP="dialout", TAG+="uaccess"
```

then `sudo udevadm control --reload-rules`.

## 2. Verify the install, no hardware

```bash
python -m pytest
python -m luminary.cli serve --seed-demo
```

Open <http://localhost:8080>, pick `pentagon-4A-33` and a pattern, press
Play. Everything on screen went through the real wire codec. If this works,
the software is good and anything that fails later is hardware.

`pytest` skips the JS and C++ decoder conformance tests when `node` and
`g++` are absent — install them (node **22+**) or those checks silently do
not run.

## 3. Register the boards

Plug the boards in and:

```bash
python -m luminary.cli boards
```

Each board must pass both an Adafruit USB identity check and a protocol
probe, so USB-serial adapters and other devices on the bus are never
mistaken for boards. Results are written to `var/boards.yaml`, keyed by
controller id.

Act on anything that is not a plain board:

| Reported | Means |
|---|---|
| `bootsel` | No usable firmware. Flash it (step 4). |
| `blocked` | Port not openable. The dialout group, step 1. |
| `unresponsive` | Enumerates, does not answer. Re-flash. |
| duplicate ids | Two boards share one id and drive the same lights. Re-flash one. |

`-v` lists every device considered and why it was rejected.

## 4. Flash

```bash
pip install platformio
python -m luminary.cli flash --max-per-strip 180
```

Set `--max-per-strip` to your longest strip. Every frame clocks out that
many pixels on all eight outputs whatever the geometry uses, so
overshooting costs frame rate directly.

A board with working firmware is reset into its bootloader automatically.
A board that has never been flashed will not be: hold **BOOTSEL** while
plugging it in, confirm `boards` shows `bootsel`, then flash.

Flash one board at a time — the bootloader volume is not addressable per
board:

```bash
python -m luminary.cli flash --controller 3 --max-per-strip 180
```

Each flash ends with an identity probe, so "ok" means the board came back
and answered with the id it was built for. Anything else is a failure with
the reason.

Re-run `boards` afterwards to register the new device nodes.

## 5. Map

```bash
python -m luminary.cli map                 # TUI
python -m luminary.cli map --web           # browser instead
python -m luminary.cli map --continue      # resume
```

Stage A locks each board to its planned position; stage B records channel,
density, and winding per panel. The session explains itself as it goes and
saves one YAML per board under `var/mapping/` after every step, so it is
safe to stop at any point.

Practise first, no hardware needed, at
<http://localhost:8080/demo/mapping>.

## 6. Show

```bash
python -m luminary.cli show --lights pentagon-4A-33 --pattern aurora
```

Streams to every registered board and mirrors the same bytes to
<http://localhost:8080/preview>. The preview is a mirror, not a second
render — one engine feeds both — so it is evidence of what the boards
received. Its header carries the wire health: boards up, ACK latency,
window stalls, and the adaptive byte budget.

`--serial 0=/dev/ttyACM0,1=/dev/ttyACM1` overrides discovery. `--host
0.0.0.0` exposes the preview to the network.

A slow browser loses preview frames and never slows the boards.

## Limits

- **4096 active lights per board.** Above it the board refuses the geometry
  and runs a rainbow test pattern — running beads instead of your pattern
  means exactly this.
- Frame rate is 30 fps. Under load the sender shrinks per-frame DELTA detail
  to protect pacing rather than dropping frames.

## Known gap: multi-board geometry

`map` records the per-board YAMLs, but the pentagon capture does not yet
consume them — it assigns every light to controller 0. Until that lands,
`show` drives a single board. Multi-board deployments need the identity
assignment in `luminary/geometry/pentagon/adapters.py` (`capture`, spec
§7.3.1).

## When something breaks

Boards recover on their own: a board that drops is retried every second and
re-sent its geometry, a board that reboots is detected and re-synced, and a
firmware hang is caught by an 8 s watchdog. Nothing here needs a human
unless the hardware is genuinely dead.

Start with `python -m luminary.cli boards -v`. It answers "is the board
there, and is it really a board" before anything else is worth checking.
