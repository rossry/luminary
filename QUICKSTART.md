# Quickstart — production deployment

```bash
./install.sh                 # venv, deps, board access, udev rules
. .venv/bin/activate
```

Then, with the boards on USB:

```bash
luminary boards                        # find, verify, register
luminary flash --max-per-strip 180     # set to that board's longest strip
luminary map                           # interactive; explains itself
luminary geometry                      # mapping records -> deployed geometry
luminary show --lights <id> --pattern aurora
```

`show` streams to every board and mirrors the same wire bytes to
<http://localhost:8080/preview>.

## When it doesn't work

`luminary boards` first — it says whether a thing on USB is a board, and if
not, why:

| | |
|---|---|
| `bootsel` | No usable firmware. Hold BOOTSEL while plugging in, then `flash`. |
| `blocked` | Port not openable. Re-run `install.sh`, then log out and in. |
| `unresponsive` | Enumerates, doesn't answer. Re-flash. |
| duplicate ids | Two boards driving the same lights. Re-flash one. |

A board that has never been flashed does not enumerate at all.

## Limits

**4096 active lights per board** — above it the board refuses the geometry and
runs a rainbow test pattern, which is what running beads mean.

Frame rate is 30 fps. `--max-per-strip` is per board and sets the ceiling
directly (180 is worth roughly double 360), so flash 180 only where every
strip on that board is 180 — a longer strip under it goes half dark.

Add `--interpolate` to `geometry` if a board carries several 360-LED strips.

Boards recover on their own: dropped boards retry every second, reboots
re-sync, hangs hit an 8 s watchdog.

More: [`README.md`](README.md), [`plan/mapping/DESCRIPTION.md`](plan/mapping/DESCRIPTION.md).
