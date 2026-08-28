# Quickstart — production deployment

```bash
./install.sh                 # venv, deps, board access, udev rules
. .venv/bin/activate
```

Then, with the boards on USB:

```bash
luminary boards      # find, verify, register
luminary flash       # build, flash, verify each board answers
luminary map         # interactive; explains itself
luminary geometry    # mapping records -> deployed geometry
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

Frame rate is 30 fps. Strips are 360 LEDs unless a board's are all 180, and
`flash` builds for 360 until the mapping says otherwise — so **flash again
after mapping**, when it can read each board's longest strip from the records
and build the exceptional all-180 board for 180, which is worth roughly double
the frame rate. Setting `--max-per-strip` by hand below a board's longest
strip leaves the rest of that strip dark.

Add `--interpolate` to `geometry` if a board carries several 360-LED strips.

Boards recover on their own: dropped boards retry every second, reboots
re-sync, hangs hit an 8 s watchdog.

More: [`README.md`](README.md), [`plan/mapping/DESCRIPTION.md`](plan/mapping/DESCRIPTION.md).
