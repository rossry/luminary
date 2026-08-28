"""The mapping sequence as a pure state machine.

`step(state, plan, event) -> state` — no I/O, no clocks, no surfaces.
Adapters translate keys to events (arrows and WASD are equivalent) and
react to the returned state (persist, rebuild the session, redraw).

Stages (plan/mapping/DESCRIPTION.md):
  ports  — per board: <-/-> cycles which probed controller id breathes;
           enter locks controller <-> planned unit and advances.
  panels — per panel: <-/-> cycles the candidate channel; up toggles
           density (180/360) **of the selected strip** (board x channel,
           not the panel — density is a property of the strip physically
           plugged into that channel, so it stays with the channel when a
           panel moves); down toggles winding (cw/ccw); one enter records
           all three and advances. A completed board flips to the mapped
           pattern and the next board begins.
  done   — everything mapped; progress markers are cleared.

Two ways in. ``initial_state`` walks every slot from the start with the
saved records pre-loaded as the candidates, so an operator re-running a
mapping that is already right holds enter through it and only stops where
something changed. ``resume_state`` (--continue) instead skips ahead to the
first slot that has never been recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple

from luminary.mapping.plan import Face, Plan


class Event(Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    ENTER = "enter"


@dataclass(frozen=True)
class ChannelRecord:
    face: Face
    winding: str  # "cw" | "ccw" (from the six-red corner, seen from outside)
    density: int  # 180 | 360


@dataclass(frozen=True)
class BoardRecord:
    unit_vertex: int
    controller_id: Optional[int] = None  # locked in the ports stage
    channels: Dict[int, ChannelRecord] = field(default_factory=dict)
    # Density per channel, independent of which panel is on it: the strip
    # plugged into a channel has the LED density it has, and that does not
    # change when the operator assigns a different panel to it. Seeded from
    # the channel records on load; `channels[ch].density` stays the
    # persisted truth.
    densities: Dict[int, int] = field(default_factory=dict)

    def density_for(self, channel: int) -> int:
        """The density recorded for this physical strip, else the default."""
        if channel in self.densities:
            return self.densities[channel]
        record = self.channels.get(channel)
        return record.density if record is not None else 180


@dataclass(frozen=True)
class MappingState:
    stage: str  # "ports" | "panels" | "done"
    boards: Dict[int, BoardRecord]  # unit vertex -> record
    controllers: Tuple[int, ...]  # probed controller ids, stable order
    board_cursor: int = 0  # index into plan.units
    panel_cursor: int = 0  # index into plan.panels[unit]
    # Live hypothesis, shown on wire + window until enter:
    candidate_controller: Optional[int] = None
    candidate_channel: int = 0
    candidate_winding: str = "ccw"
    candidate_density: int = 180
    # Walk every slot in order with saved values pre-filled (the default),
    # rather than skipping to the first unrecorded one (--continue).
    review: bool = False

    def board(self, plan: Plan) -> BoardRecord:
        return self.boards[plan.units[self.board_cursor]]

    def unassigned_controllers(self) -> List[int]:
        taken = {b.controller_id for b in self.boards.values()}
        return [c for c in self.controllers if c not in taken]

    def free_channels(self, plan: Plan) -> List[int]:
        """Channels the cursor may offer for the panel under it.

        In review mode the panel's own recorded channel stays on offer —
        otherwise re-confirming an already-correct mapping would be
        impossible, since its channel reads as taken.
        """
        board = self.board(plan)
        used = set(board.channels)
        if self.review:
            panel = plan.panels[plan.units[self.board_cursor]][self.panel_cursor]
            for channel, record in board.channels.items():
                if record.face == panel.face:
                    used.discard(channel)
        return [ch for ch in range(8) if ch not in used]


def initial_state(
    plan: Plan,
    controllers: List[int],
    boards: Optional[Dict[int, BoardRecord]] = None,
) -> MappingState:
    """Start at the beginning, with any saved records pre-filled.

    Passing ``boards`` does not skip anything: the sequence still runs from
    the first board and the first panel. What it changes is the candidate at
    each stop — it is the saved value, so every step that is already correct
    is a single enter.
    """
    merged = {v: (boards or {}).get(v, BoardRecord(unit_vertex=v)) for v in plan.units}
    merged = {v: replace(b, densities=_seed_densities(b)) for v, b in merged.items()}
    state = MappingState(
        stage="ports",
        boards=merged,
        controllers=tuple(controllers),
        review=True,
    )
    return _land(state, plan)


def _seed_densities(board: BoardRecord) -> Dict[int, int]:
    """Per-channel densities from the persisted channel records."""
    seeded = {ch: rec.density for ch, rec in board.channels.items()}
    seeded.update(board.densities)
    return seeded


def resume_state(
    plan: Plan, controllers: List[int], boards: Dict[int, BoardRecord]
) -> MappingState:
    """Rebuild from saved records (--continue); cursors land on the first
    unassigned board / unmapped panel."""
    merged = {v: boards.get(v, BoardRecord(unit_vertex=v)) for v in plan.units}
    merged = {v: replace(b, densities=_seed_densities(b)) for v, b in merged.items()}
    stage = "ports"
    if all(b.controller_id is not None for b in merged.values()):
        stage = "panels"
        if all(len(merged[v].channels) == len(plan.panels[v]) for v in plan.units):
            stage = "done"
    state = MappingState(stage=stage, boards=merged, controllers=tuple(controllers))
    return _land(state, plan)


def _land(state: MappingState, plan: Plan) -> MappingState:
    """Put the cursor on its next slot and refresh the candidates.

    Review mode stops at every slot in order and offers the saved value;
    --continue skips to the first slot that has never been recorded.
    """
    if state.stage == "ports":
        for i, v in enumerate(plan.units):
            if state.review and i < state.board_cursor:
                continue
            if state.review or state.boards[v].controller_id is None:
                saved = state.boards[v].controller_id
                free = state.unassigned_controllers()
                candidate = saved if saved is not None else (free[0] if free else None)
                return replace(state, board_cursor=i, candidate_controller=candidate)
        state = replace(state, stage="panels", board_cursor=0, panel_cursor=0)
    if state.stage == "panels":
        for i, v in enumerate(plan.units):
            if state.review and i < state.board_cursor:
                continue
            board = state.boards[v]
            for j, panel in enumerate(plan.panels[v]):
                if state.review and i == state.board_cursor and j < state.panel_cursor:
                    continue
                saved_channel = next(
                    (ch for ch, r in board.channels.items() if r.face == panel.face),
                    None,
                )
                if not state.review and saved_channel is not None:
                    continue
                probe = replace(state, board_cursor=i, panel_cursor=j)
                free = probe.free_channels(plan)
                channel = (
                    saved_channel
                    if saved_channel is not None
                    else (free[0] if free else 0)
                )
                saved_record = board.channels.get(channel)
                return replace(
                    probe,
                    candidate_channel=channel,
                    candidate_winding=(saved_record.winding if saved_record else "ccw"),
                    candidate_density=board.density_for(channel),
                )
        state = replace(state, stage="done")
    return state


def _cycle(options: List[int], current: Optional[int], delta: int) -> Optional[int]:
    if not options:
        return None
    if current not in options:
        return options[0]
    return options[(options.index(current) + delta) % len(options)]


def step(state: MappingState, plan: Plan, event: Event) -> MappingState:
    if state.stage == "ports":
        free = state.unassigned_controllers()
        if event is Event.LEFT or event is Event.RIGHT:
            delta = -1 if event is Event.LEFT else 1
            return replace(
                state,
                candidate_controller=_cycle(free, state.candidate_controller, delta),
            )
        if event is Event.ENTER and state.candidate_controller is not None:
            unit = plan.units[state.board_cursor]
            boards = dict(state.boards)
            boards[unit] = replace(
                boards[unit], controller_id=state.candidate_controller
            )
            advanced = (
                replace(state, boards=boards, board_cursor=state.board_cursor + 1)
                if state.review
                else replace(state, boards=boards)
            )
            return _land(advanced, plan)
        return state

    if state.stage == "panels":
        if event is Event.LEFT or event is Event.RIGHT:
            delta = -1 if event is Event.LEFT else 1
            nxt = _cycle(state.free_channels(plan), state.candidate_channel, delta)
            channel = nxt if nxt is not None else 0
            # Density belongs to the strip, so selecting a channel shows that
            # strip's density rather than carrying the last one over.
            return replace(
                state,
                candidate_channel=channel,
                candidate_density=state.board(plan).density_for(channel),
            )
        if event is Event.UP:
            # Toggle the *strip's* density (board x channel) and remember it
            # there, so it survives the panel moving to another channel.
            density = 360 if state.candidate_density == 180 else 180
            unit = plan.units[state.board_cursor]
            boards = dict(state.boards)
            densities = dict(boards[unit].densities)
            densities[state.candidate_channel] = density
            boards[unit] = replace(boards[unit], densities=densities)
            return replace(state, boards=boards, candidate_density=density)
        if event is Event.DOWN:
            return replace(
                state,
                candidate_winding="cw" if state.candidate_winding == "ccw" else "ccw",
            )
        if event is Event.ENTER:
            unit = plan.units[state.board_cursor]
            panel = plan.panels[unit][state.panel_cursor]
            boards = dict(state.boards)
            channels = dict(boards[unit].channels)
            # A panel that moved to a different channel must not leave a copy
            # of itself behind on the old one.
            for ch, rec in list(channels.items()):
                if rec.face == panel.face and ch != state.candidate_channel:
                    del channels[ch]
            channels[state.candidate_channel] = ChannelRecord(
                face=panel.face,
                winding=state.candidate_winding,
                density=state.candidate_density,
            )
            densities = dict(boards[unit].densities)
            densities[state.candidate_channel] = state.candidate_density
            boards[unit] = replace(boards[unit], channels=channels, densities=densities)
            moved = replace(state, boards=boards)
            if state.review:
                panels = plan.panels[unit]
                if state.panel_cursor + 1 < len(panels):
                    moved = replace(moved, panel_cursor=state.panel_cursor + 1)
                else:
                    moved = replace(
                        moved, board_cursor=state.board_cursor + 1, panel_cursor=0
                    )
            return _land(moved, plan)

    return state  # done: inert
