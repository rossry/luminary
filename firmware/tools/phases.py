"""Per-phase board timing: where a frame's microseconds actually go.

ACK round trip folds decode, render and DMA into one number, so it cannot say
which of them moved when something changes. The firmware accumulates each
phase separately and reports once a second as a STATS frame (spec §13.7);
this replays a real geometry and prints the breakdown.

    python firmware/tools/phases.py --port /dev/ttyACM0 --channels 8 \
        --per-strip 360 --fps 60 --seconds 12
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import serial  # noqa: E402

from luminary.comms import protocol as p  # noqa: E402
from luminary.comms.codec import CodecConfig  # noqa: E402
from luminary.engine.engine import Engine  # noqa: E402
from luminary.patterns.registry import default_registry  # noqa: E402

sys.path.insert(0, str(REPO / "firmware" / "tools"))
from bench import synth  # noqa: E402

BAUD = 2_000_000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--channels", type=int, default=8)
    ap.add_argument("--per-strip", type=int, default=360)
    ap.add_argument("--interpolate-every", type=int, default=0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument(
        "--warmup",
        type=float,
        default=1.0,
        help="Seconds of reports to discard. The clock's minimum filter only "
        "republishes when a 64-observation window closes -- 2.1 s at 30 fps "
        "-- so early reports measure acquisition, not steady state.",
    )
    ap.add_argument(
        "--window",
        type=int,
        default=4,
        help="Max frames in flight; must exceed the board's "
        "play-out queue depth or it throttles the queue",
    )
    args = ap.parse_args()

    lights = synth(args.channels, args.per_strip, args.interpolate_every)
    engine = Engine(
        lights,
        default_registry().get("aurora"),
        fps=args.fps,
        codec_config=CodecConfig(budget_bytes=args.budget),
    )
    conn = serial.Serial(args.port, baudrate=BAUD, timeout=0, write_timeout=2.0)
    splitter = p.FrameSplitter()
    try:
        time.sleep(0.3)
        conn.reset_input_buffer()
        for frame in engine.session_frames():
            conn.write(frame)
        conn.flush()
        time.sleep(0.3)

        reports = []
        acks = 0
        interval = 1.0 / args.fps
        start = time.perf_counter()
        next_due = start
        i = 0
        sent = 0
        while time.perf_counter() - start < args.seconds:
            now = time.perf_counter()
            # Respect an acknowledgement window. Without one this floods the
            # board, its USB buffer backs up, and the write blocks -- which
            # reads exactly like a board fault and is really the tool's fault
            # (the same trap bench.py documents).
            if now >= next_due and (sent - acks) < args.window:
                for frame in engine.frame(i / args.fps):
                    conn.write(frame)
                i += 1
                sent += 1
                next_due += interval
            elif now >= next_due:
                next_due += interval  # skipped: window full
            for raw in splitter.feed(conn.read(8192)):
                try:
                    kind, _, _, payload = p.parse_frame(raw)
                except p.ProtocolError:
                    continue
                if kind == p.FRAME_ACK:
                    acks += 1
                elif kind == p.FRAME_STATS:
                    reports.append(p.parse_stats_payload(payload))
    finally:
        conn.close()

    elapsed = time.perf_counter() - start
    # Reports arrive about once a second; drop the warmup window.
    dropped = min(len(reports), max(1, int(round(args.warmup))))
    reports = reports[dropped:]
    if not reports:
        print("no STATS frames -- is the board running instrumented firmware?")
        return 1

    print(
        f"\ngeometry   : {args.channels} x {args.per_strip}"
        f"{'' if not args.interpolate_every else f' (1-in-{args.interpolate_every} interpolated)'}"
        f"   nActive={reports[-1]['n_active']}"
    )
    print(f"host       : {i} frames requested at {args.fps} fps over {elapsed:.1f}s")
    print(f"board      : {sum(r['frames'] for r in reports)} shown, {acks} acked")
    print(f"\n{'phase':<12}{'us/frame':>10}{'% of frame':>12}")
    total_frames = sum(r["frames"] for r in reports) or 1
    budget_us = 1e6 / args.fps
    phases = ("decode_us", "predict_us", "convert_us", "stage_us", "show_us")
    grand = 0
    for phase in phases:
        per = sum(r[phase] for r in reports) / total_frames
        grand += per
        print(f"{phase[:-3]:<12}{per:>10.0f}{per / budget_us * 100:>11.1f}%")
    print(f"{'TOTAL':<12}{grand:>10.0f}{grand / budget_us * 100:>11.1f}%")
    print(
        f"\nboard fps  : {total_frames / (len(reports)):.1f} "
        f"(ceiling {1e6 / grand:.1f} if nothing overlapped)"
    )
    print(
        f"loop max   : {max(r['loop_max_us'] for r in reports)} us"
        f"   (frame budget {budget_us:.0f} us)"
    )
    if "queue_slots" in reports[0]:
        slots = reports[-1]["queue_slots"]
        queued = sum(r["queue_depth_sum"] for r in reports) / total_frames
        late = sum(r["late_frames"] for r in reports)
        print(
            f"queue      : {slots} slots, {queued:.2f} deep on average, "
            f"{late} shown late (past deadline by over a frame)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
