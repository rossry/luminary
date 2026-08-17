"""Host-side hardware bench for the Scorpio firmware.

Measures what the board can actually do, as opposed to what the wire can
carry. These are different by an order of magnitude and conflating them has
produced wrong conclusions more than once, so the tooling keeps them apart.

Subcommands:

  capability  frames/second and true ACK round-trip the board sustains for a
              given geometry, with the host taken out of the way
  overdrive   push past the window and check the board survives -- the RP2040
              USB stack wedges rather than applying backpressure (spec 11.7.6)
  sweep       vary the per-frame byte budget and watch frame rate respond
  geometry    print the shape of a synthetic geometry without touching hardware

Two measurement traps this avoids, both of which produced bogus numbers
before:

  * Pacing with time.sleep() -- Windows rounds it to ~15.6ms, so a loop that
    thinks it is pacing 30fps delivers ~24. All pacing here busy-waits on
    perf_counter.
  * Wrapping a payload buffer by restarting at index 0 -- that truncates the
    frame in flight and desyncs COBS, which the board correctly reports as
    corruption and reads exactly like a bad cable. Frames are written whole.

    python firmware/tools/bench.py capability --port COM8 --channels 6 --per-strip 360
    python firmware/tools/bench.py overdrive --port COM8 --seconds 20
    python firmware/tools/bench.py sweep --port COM8 --budgets 5333,2000,800
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import serial

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from luminary.comms import protocol as p  # noqa: E402
from luminary.comms.codec import CodecConfig  # noqa: E402
from luminary.engine.engine import Engine  # noqa: E402
from luminary.geometry.lights import (  # noqa: E402
    Kind,
    LightColumns,
    LightsGeometry,
    N_LIGHT_COLUMNS,
    SpaceSpec,
)
from luminary.patterns.registry import default_registry  # noqa: E402

GOLDEN = REPO / "firmware" / "golden" / "case1"
BAUD = 2_000_000


# ------------------------------------------------------------------ geometry


def synth(channels: int, per_strip: int, interpolate_every: int = 0,
          controller: int = 0) -> LightsGeometry:
    """N strips of M physical LEDs, laid out as horizontal runs.

    ``interpolate_every=2`` makes every other light INTERPOLATED -- the "180
    on the wire, 360 on the strip" arrangement. That halves wire size and
    decode cost but NOT the repaint: DMA time and per-pixel colour conversion
    scale with physical LEDs, not with ACTIVE ones.
    """
    n = channels * per_strip
    array = np.zeros((n, N_LIGHT_COLUMNS), dtype=float)
    row = 0
    for channel in range(channels):
        for index in range(per_strip):
            interpolated = (
                interpolate_every > 1
                and index % interpolate_every != 0
                and index != per_strip - 1
            )
            array[row, LightColumns.CONTROLLER] = controller
            array[row, LightColumns.CHANNEL] = channel
            array[row, LightColumns.INDEX] = index
            array[row, LightColumns.KIND] = (
                Kind.INTERPOLATED if interpolated else Kind.ACTIVE
            )
            array[row, LightColumns.WEIGHT] = 128 if interpolated else 0
            array[row, LightColumns.X] = float(index)
            array[row, LightColumns.Y] = float(channel * 10)
            row += 1
    return LightsGeometry(
        array=array,
        display=[None] * n,
        space=SpaceSpec(authoritative=["xy"]),
        source={"kind": "synthetic", "note": "bench"},
        meta={"name": f"bench-{channels}x{per_strip}"},
    )


# -------------------------------------------------------------------- shared


def parse(raw):
    try:
        return p.parse_frame(raw)
    except p.ProtocolError:
        return None


def flush_boundary(conn, seconds: float = 0.25):
    """Terminate any partial frame so measurement starts at a clean edge."""
    conn.write(b"\x00" * 4)
    time.sleep(seconds)
    conn.reset_input_buffer()
    return p.FrameSplitter()


def encode_frames(lights, budget, count, pattern="wave", fps=30.0):
    config = CodecConfig()
    if budget:
        config.budget_bytes = budget
    engine = Engine(lights, default_registry().get(pattern), fps=fps,
                    codec_config=config)
    session = list(engine.session_frames())
    frames = []
    for i in range(count):
        frames.extend(engine.frame(i / fps))
    return session, frames


def frame_t(frame: bytes) -> float:
    body = p.cobs_decode(frame.rstrip(b"\x00"))
    return p.parse_frame(body)[2]


def still_alive(port: str) -> bool:
    time.sleep(1.0)
    try:
        conn = serial.Serial(port, baudrate=BAUD, timeout=0)
        conn.close()
        return True
    except Exception:
        return False


def windowed_push(conn, splitter, frames, window, seconds, precomputed_t=None):
    """Push frames bounded only by the ACK window. Returns a stats dict.

    Reads inbound every iteration rather than once per tick, so the latency
    figure is a real write->ACK round trip and not the tick period.
    """
    pending: deque = deque()
    latencies = []
    sent = acked = resyncs = 0
    stalled = False
    idx = 0
    started = time.perf_counter()
    deadline = started + seconds
    while time.perf_counter() < deadline:
        data = conn.read(8192)
        if data:
            for raw in splitter.feed(data):
                frame = parse(raw)
                if frame is None:
                    continue
                if frame[0] == p.FRAME_ACK:
                    now = time.perf_counter()
                    while pending:
                        t, sent_at = pending.popleft()
                        latencies.append((now - sent_at) * 1000.0)
                        acked += 1
                        if t >= frame[2]:
                            break
                elif frame[0] == p.FRAME_RESYNC:
                    resyncs += 1
        if len(pending) >= window:
            continue
        i = idx % len(frames)
        frame = frames[i]
        idx += 1
        t = precomputed_t[i] if precomputed_t else frame_t(frame)
        try:
            conn.write(frame)
        except serial.SerialTimeoutException:
            stalled = True
            break
        pending.append((t, time.perf_counter()))
        sent += 1
    elapsed = time.perf_counter() - started
    return {
        "sent": sent, "acked": acked, "resyncs": resyncs,
        "stalled": stalled, "elapsed": elapsed,
        "fps": sent / elapsed if elapsed else 0.0,
        "latencies": sorted(latencies),
    }


def report(stats, mean_bytes=None):
    print(f"  frames pushed  : {stats['sent']} in {stats['elapsed']:.1f}s "
          f"= {stats['fps']:.1f} fps")
    if mean_bytes:
        rate = stats["sent"] * mean_bytes / stats["elapsed"] / 1024
        print(f"  throughput     : {rate:.1f} KiB/s "
              f"(mean frame {mean_bytes:.0f} B)")
    print(f"  RESYNC         : {stats['resyncs']}"
          f"{'   WRITE STALLED' if stats['stalled'] else ''}")
    lat = stats["latencies"]
    if lat:
        print(f"  ACK rtt        : n={len(lat)} "
              f"median={statistics.median(lat):.2f}ms "
              f"p95={lat[int(len(lat) * 0.95) - 1]:.2f}ms max={lat[-1]:.2f}ms")
    else:
        print("  ACK rtt        : no ACKs seen (firmware predates spec 11.7.6?)")


def open_and_session(port, session, settle=0.5):
    conn = serial.Serial(port, baudrate=BAUD, timeout=0, write_timeout=2.0)
    time.sleep(0.3)
    flush_boundary(conn)
    for frame in session:
        conn.write(frame)
    time.sleep(settle)
    conn.reset_input_buffer()
    return conn, p.FrameSplitter()


# ---------------------------------------------------------------- subcommands


def cmd_geometry(args):
    lights = synth(args.channels, args.per_strip, args.interpolate_every)
    active = int(lights.control_mask.sum())
    print(f"{lights.meta['name']}: n={lights.n} active={active} "
          f"interpolated={lights.n - active}")
    session, frames = encode_frames(lights, args.budget, 60)
    mean = sum(len(f) for f in frames) / max(1, len(frames))
    print(f"  session {len(session)} frame(s), "
          f"{sum(len(f) for f in session)} bytes")
    print(f"  steady-state mean frame: {mean:.0f} bytes "
          f"({mean * 30 / 1024:.1f} KiB/s at 30fps)")
    return 0


def cmd_capability(args):
    lights = synth(args.channels, args.per_strip, args.interpolate_every)
    active = int(lights.control_mask.sum())
    print(f"geometry: n={lights.n} active={active} "
          f"({args.channels}x{args.per_strip})")
    session, frames = encode_frames(lights, args.budget, args.precount)
    mean = sum(len(f) for f in frames) / max(1, len(frames))
    times = [frame_t(f) for f in frames]
    print(f"  {len(frames)} frames encoded, mean {mean:.0f} bytes, "
          f"window={args.window}\n")

    conn, splitter = open_and_session(args.port, session)
    try:
        stats = windowed_push(conn, splitter, frames, args.window,
                              args.seconds, times)
    finally:
        conn.close()

    print("-- board capability --")
    report(stats, mean)
    alive = still_alive(args.port)
    print(f"  board alive    : {'yes' if alive else 'NO -- wedged'}")
    headroom = stats["fps"] / args.target
    print(f"\n  vs {args.target:.0f} fps target: {headroom:.2f}x "
          f"({'PASS' if headroom >= 1.0 and alive else 'SHORT'})")
    return 0 if headroom >= 1.0 and alive else 1


def cmd_overdrive(args):
    """Push as hard as the window allows and check the board survives."""
    stream = (GOLDEN / "stream.bin").read_bytes()
    frames, start = [], 0
    for i, byte in enumerate(stream):
        if byte == 0:
            frames.append(stream[start:i + 1])
            start = i + 1
    times = [frame_t(f) for f in frames]
    print(f"overdrive: {len(frames)} golden frames on repeat, "
          f"window={args.window}, {args.seconds:.0f}s")
    print("  (this is the test that wedged the board before flow control)\n")

    conn = serial.Serial(args.port, baudrate=BAUD, timeout=0, write_timeout=2.0)
    try:
        time.sleep(0.3)
        splitter = flush_boundary(conn)
        stats = windowed_push(conn, splitter, frames, args.window,
                              args.seconds, times)
    finally:
        conn.close()

    report(stats)
    alive = still_alive(args.port)
    print(f"  board alive    : {'yes' if alive else 'NO -- wedged, needs replug'}")
    ok = alive and not stats["stalled"]
    print(f"\n  {'PASS: window held' if ok else 'FAIL: window did not protect the board'}")
    return 0 if ok else 1


def cmd_sweep(args):
    lights = synth(args.channels, args.per_strip, args.interpolate_every)
    budgets = [int(b) for b in args.budgets.split(",")]
    print(f"geometry: n={lights.n} active={int(lights.control_mask.sum())}")
    print(f"\n  budget   mean frame   fps    ACK rtt median   RESYNC")
    for budget in budgets:
        session, frames = encode_frames(lights, budget, args.precount)
        mean = sum(len(f) for f in frames) / max(1, len(frames))
        times = [frame_t(f) for f in frames]
        conn, splitter = open_and_session(args.port, session)
        try:
            stats = windowed_push(conn, splitter, frames, args.window,
                                  args.seconds, times)
        finally:
            conn.close()
        lat = stats["latencies"]
        med = statistics.median(lat) if lat else float("nan")
        print(f"  {budget:6d}   {mean:9.0f}B   {stats['fps']:5.1f}  "
              f"{med:13.2f}ms   {stats['resyncs']:4d}"
              f"{'  STALLED' if stats['stalled'] else ''}")
        if not still_alive(args.port):
            print("  board wedged -- stopping sweep")
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(q, hardware=True):
        if hardware:
            q.add_argument("--port", required=True)
            q.add_argument("--window", type=int, default=4)
            q.add_argument("--seconds", type=float, default=12.0)
        q.add_argument("--channels", type=int, default=6)
        q.add_argument("--per-strip", type=int, default=360)
        q.add_argument("--interpolate-every", type=int, default=0)
        q.add_argument("--budget", type=int, default=800)
        q.add_argument("--precount", type=int, default=200)

    q = sub.add_parser("capability", help="board fps ceiling and true ACK rtt")
    common(q)
    q.add_argument("--target", type=float, default=30.0)
    q.set_defaults(func=cmd_capability)

    q = sub.add_parser("overdrive", help="check the window protects the board")
    q.add_argument("--port", required=True)
    q.add_argument("--window", type=int, default=4)
    q.add_argument("--seconds", type=float, default=20.0)
    q.set_defaults(func=cmd_overdrive)

    q = sub.add_parser("sweep", help="frame rate vs per-frame byte budget")
    common(q)
    q.add_argument("--budgets", default="5333,3000,2000,1200,800")
    q.set_defaults(func=cmd_sweep)

    q = sub.add_parser("geometry", help="describe a synthetic geometry")
    common(q, hardware=False)
    q.set_defaults(func=cmd_geometry)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
