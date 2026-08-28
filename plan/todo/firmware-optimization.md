# Firmware optimization — working state

Live work on board headroom. Target: butter-smooth 60 fps at 8x360, relaxed
to 30 fps in production so the margin is spare capacity rather than budget.

Measure with `firmware/tools/phases.py` (board-side per-phase timing over a
STATS frame, spec §13.7). ACK round trip folds decode, render and DMA into
one number and cannot say which of them moved.

```bash
python -m luminary.cli flash --controller 0 --max-per-strip 360
python firmware/tools/phases.py --port /dev/ttyACM0 --channels 8 \
    --per-strip 360 --fps 60 --seconds 10
cd firmware/test/host && make -s && ./test_decoder ../../golden/case1
```

## Where it stands (8x360, 60 fps requested)

| phase | µs/frame | note |
|---|---|---|
| decode | 4169 | includes predictor |
| predictor | 2407 | O(nActive) |
| conversion | 4995 | O(physical LEDs) — largest remaining |
| stage | 395 | |
| show | 2426 | DMA already overlaps; not the 10.8 ms floor |
| **total** | **14391** | 86% of a 16.7 ms budget |

Board: 48.8 fps at 8x360, 50.6 fps at 8x180. Was 36.7 fps before the
conversion fix.

## Done

**LMS→RGB at Q13 instead of Q14** (commit 32c0e8e). The last int64
accumulator became nine `__aeabi_lmul` calls per pixel on a part with no
64-bit multiply. Q13 puts the peak at 1.02e9, safely int32. Conversion
11080 → 4995 µs; 36.7 → 48.8 fps; worst loop 143 ms → 18.8 ms. Held to the
conformance test's ±2/255 RGB tolerance; quantised state stays bit-exact.

**Per-phase instrumentation.** `FRAME_STATS = 6`, board→host only, off the
render path so outside the three-decoder rule.

## Disproved — do not retry without new evidence

**Narrowing `q_`/`v_` from 24 bytes/light to 9** (uint8 + int16) measured
WORSE: predictor 2407 → 2531 µs, conversion 4995 → 5235 µs, 48.8 → 47.1 fps.
ARMv6-M has no free narrow access — every byte/halfword load needs an
extension instruction — and these loops are instruction-bound, not
memory-bound. The RAM saving only buys headroom against MAX_ACTIVE_LIGHTS,
and the busiest real board uses 1440 of 4096.

## Remaining, in order

### 1. Drop the 15 ms repaint gate

`main.cpp`: `due && now - lastShowMs >= 15` hard-caps ~66 fps and quantises
every repaint. 60 fps is unreachable while it stands. Cheapest change here.

### 2. Inter-board sync + play-out buffer

**There is currently no sync at all.** Each board paints when its own
`dirty && canShow()` allows; the header `t` is only echoed in the ACK. Skew
sources: sequential `_route` writes, per-board decode time (~2.3 ms measured
between a 6-panel and an 8-panel board), the 15 ms gate free-running per
board, and `canShow()` blocking on that board's DMA. Worst case approaches
half a frame — invisible on gradients, visible on a hard cut.

Design: board estimates `epoch = local_micros - t*1e6` using a **minimum**
filter over recent frames (NTP-style: minimum rejects queuing delay and
converges on true offset; a mean would bake each board's own delivery
latency into its offset). Present frame `t` at `epoch + t*1e6 + D`, with D a
fixed display delay greater than worst-case delivery jitter (start ~3
frames). All boards fed one host stream converge on the same epoch, so the
constant D makes them present together.

ACK semantics change: today an ACK means "consumed and rendered", which is
what makes the window safe. With a queue it becomes "enqueued", and queue
depth joins the window arithmetic — otherwise the sender double-counts the
buffering and runs further ahead than intended.

### 3. Core1 — split by determinism, not by load

Core1 takes the whole path from decoded state to pixels: conversion, stage,
show (7.8 ms, fixed cost, hard deadline). Core0 keeps everything variable:
USB, COBS, CRC, decode, predictor, ACK, watchdog — no deadline, it only has
to keep the queue fed. Constant work against a deadline is schedulable; that
is the reliability argument.

Rejected: "core1 lightly loaded with only `show()`" leaves conversion — the
largest deadline-relevant cost — on the core servicing USB. Also rejected:
splitting conversion 4 channels each, which gives both cores deadline work
*and* leaves USB on core0.

Needs a `q_` snapshot per frame so the two actually overlap rather than
serialise (~34 KB at 2880 active, ~86 µs memcpy). Watch SRAM bank contention
— that is what sank the earlier NeoPXL8 double-buffering attempt.
`__scratch_x`/`__scratch_y` are separate 4 KB banks for hot small structures.

### 4. Hardware interpolators (INTERP0/INTERP1)

Two `cosInterp_q14` calls per pixel are exactly what the RP2040's
interpolator blocks do in hardware. Smallest and most speculative; do it last
against the phase harness.

## Environment

Venv at `.venv` (built with `virtualenv.pyz`; no pip/ensurepip on this box).
Node 22 at `/usr/local/lib/nodejs22` — the JS conformance test needs >= 22.
Board: one Feather RP2040 SCORPIO on `/dev/ttyACM0`, controller 0, currently
flashed `MAX_PER_STRIP=360`. udev rule at
`/etc/udev/rules.d/60-luminary-scorpio.rules` keeps it accessible across the
re-enumeration every flash causes. CPU governor pinned `performance` by
`luminary-governor.service` (p99 ACK 29.5 → 14.4 ms on the real stream).
