"""Terminal adapter: cbreak keys in, one status line out.

The surface stays thin (plan/mapping/DESCRIPTION.md "Surface-agnostic
core"): keys become Events for the pure state machine, and every state
change becomes a saved store, fresh SESSION frames for all sinks, and a
redrawn line. This is an I/O adapter — the stateless conventions of the
pattern layer deliberately do not apply here.

Keys: arrows and WASD are equivalent (left/right cycle, up density,
down winding), enter confirms, q (or ctrl-C) quits. The physical
feedback lives on the sphere and the mirror page; the status line only
names where in the sequence the operator stands.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty
from typing import List, Optional, Tuple

from luminary.mapping.session import SessionCore
from luminary.mapping.state import Event, MappingState
from luminary.mapping.store import MappingStore

_PLAIN = {
    b"w": Event.UP,
    b"a": Event.LEFT,
    b"s": Event.DOWN,
    b"d": Event.RIGHT,
    b"\r": Event.ENTER,
    b"\n": Event.ENTER,
}
_CSI = {b"A": Event.UP, b"B": Event.DOWN, b"C": Event.RIGHT, b"D": Event.LEFT}


def parse_keys(buf: bytes) -> Tuple[List[Optional[Event]], bytes]:
    """Raw stdin bytes -> (tokens, remainder). ``None`` tokens mean quit.

    The remainder holds a trailing partial escape sequence (an arrow key
    split across reads); unknown CSI triples and bare ESC are dropped.
    """
    tokens: List[Optional[Event]] = []
    i, n = 0, len(buf)
    while i < n:
        byte = buf[i : i + 1]
        if byte == b"\x1b":
            if n - i < 3:
                break  # possibly half an arrow; wait for the rest
            if buf[i + 1 : i + 2] == b"[":
                event = _CSI.get(buf[i + 2 : i + 3])
                if event is not None:
                    tokens.append(event)
                i += 3
                continue
            i += 1
            continue
        lowered = byte.lower()
        if lowered in _PLAIN:
            tokens.append(_PLAIN[lowered])
        elif lowered == b"q" or byte == b"\x03":
            tokens.append(None)
        i += 1
    return tokens, buf[i:]


def status_line(core: SessionCore) -> str:
    """One line naming where in the sequence the operator stands."""
    state, plan = core.state, core.plan
    if state.stage == "done":
        return (
            f"done — all {plan.n_panels} panels on {len(plan.units)} boards "
            "mapped; markers cleared; q quits"
        )
    unit = plan.units[state.board_cursor]
    where = f"board {state.board_cursor + 1}/{len(plan.units)} unit {unit}"
    if state.stage == "ports":
        candidate = state.candidate_controller
        shown = "-" if candidate is None else str(candidate)
        return (
            f"[ports] {where} · breathing controller {shown} · "
            "arrows/ad cycle, enter locks, q quits"
        )
    board = state.boards[unit]
    return (
        f"[panels] {where} (controller {board.controller_id}) · "
        f"panel {state.panel_cursor + 1}/{len(plan.panels[unit])} · "
        f"ch {state.candidate_channel} · {state.candidate_density}/panel · "
        f"{state.candidate_winding} · ad channel, w density, s winding, "
        "enter confirms, q quits"
    )


def run_tui(core: SessionCore, store: MappingStore, fps: float) -> None:
    """Blocking key/tick loop; returns when the operator quits.

    ``fps`` paces ``core.tick`` (the CLI passes the value the core's
    engines were built with); ``t`` is seconds since the loop started —
    the engines expect a session-relative clock. Every state change
    saves the store, restarts every sink with fresh SESSION frames (the
    rebuilt engines keyframe on their next tick), and redraws the line;
    the line is also refreshed once per second in case other output
    clobbered it.
    """
    if not sys.stdin.isatty():
        raise RuntimeError(
            "run_tui needs a terminal; use --web for the browser surface"
        )
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    def redraw() -> None:
        sys.stdout.write("\r\x1b[2K" + status_line(core))
        sys.stdout.flush()

    def resync(_state: MappingState) -> None:
        # Hooks run after the rebuild, so these are the new engines'.
        frames = core.session_frames()
        for window_sink in core.window_sinks:
            window_sink(frames["window"])
        for wire_sink in core.wire_sinks:
            wire_sink(frames["wire"])

    def persist(state: MappingState) -> None:
        store.save_state(state, core.plan)

    core.on_state_change.append(persist)
    core.on_state_change.append(resync)
    core.on_state_change.append(lambda _state: redraw())

    tty.setcbreak(fd)
    try:
        store.save_state(core.state, core.plan)  # refresh port hints on resume
        resync(core.state)
        redraw()
        interval = 1.0 / fps
        start = time.monotonic()
        next_tick = start
        last_redraw = start
        pending = b""
        while True:
            wait = max(0.0, next_tick - time.monotonic())
            readable, _, _ = select.select([fd], [], [], wait)
            if readable:
                tokens, pending = parse_keys(pending + os.read(fd, 128))
                for token in tokens:
                    if token is None:
                        return
                    core.apply(token)
            else:
                pending = b""  # a bare ESC never completes; drop it
            now = time.monotonic()
            if now >= next_tick:
                core.tick(now - start)
                next_tick += interval
                if next_tick <= now:  # fell behind: skip, never burst
                    next_tick = now + interval
            if now - last_redraw >= 1.0:
                redraw()
                last_redraw = now
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\n")
        sys.stdout.flush()
