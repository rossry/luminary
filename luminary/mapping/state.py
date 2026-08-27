"""The mapping sequence as a pure state machine.

`step(state, plan, event) -> state` — no I/O, no clocks, no surfaces.
Adapters translate keys to events (arrows and WASD are equivalent) and
react to the returned state (persist, rebuild the session, redraw).

Stages (plan/mapping/DESCRIPTION.md):
  ports  — per board: <-/-> cycles which probed controller id breathes;
           enter locks controller <-> planned unit and advances.
  panels — per panel: <-/-> cycles the candidate channel; up toggles
           density (180/360); down toggles winding (cw/ccw); one enter
           records all three and advances. A completed board flips to
           the mapped pattern and the next board begins.
  done   — everything mapped; progress markers are cleared.
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

    def board(self, plan: Plan) -> BoardRecord:
        return self.boards[plan.units[self.board_cursor]]

    def unassigned_controllers(self) -> List[int]:
        taken = {b.controller_id for b in self.boards.values()}
        return [c for c in self.controllers if c not in taken]

    def free_channels(self, plan: Plan) -> List[int]:
        used = set(self.board(plan).channels)
        return [ch for ch in range(8) if ch not in used]


def initial_state(plan: Plan, controllers: List[int]) -> MappingState:
    boards = {v: BoardRecord(unit_vertex=v) for v in plan.units}
    state = MappingState(stage="ports", boards=boards, controllers=tuple(controllers))
    return _land(state, plan)


def resume_state(
    plan: Plan, controllers: List[int], boards: Dict[int, BoardRecord]
) -> MappingState:
    """Rebuild from saved records (--continue); cursors land on the first
    unassigned board / unmapped panel."""
    merged = {v: boards.get(v, BoardRecord(unit_vertex=v)) for v in plan.units}
    stage = "ports"
    if all(b.controller_id is not None for b in merged.values()):
        stage = "panels"
        if all(len(merged[v].channels) == len(plan.panels[v]) for v in plan.units):
            stage = "done"
    state = MappingState(stage=stage, boards=merged, controllers=tuple(controllers))
    return _land(state, plan)


def _land(state: MappingState, plan: Plan) -> MappingState:
    """Move cursors to the next open slot and refresh candidates."""
    if state.stage == "ports":
        for i, v in enumerate(plan.units):
            if state.boards[v].controller_id is None:
                free = state.unassigned_controllers()
                return replace(
                    state,
                    board_cursor=i,
                    candidate_controller=free[0] if free else None,
                )
        state = replace(state, stage="panels")
    if state.stage == "panels":
        for i, v in enumerate(plan.units):
            board = state.boards[v]
            for j, panel in enumerate(plan.panels[v]):
                if not any(rec.face == panel.face for rec in board.channels.values()):
                    probe = replace(state, board_cursor=i)
                    free = probe.free_channels(plan)
                    return replace(
                        probe,
                        panel_cursor=j,
                        candidate_channel=free[0] if free else 0,
                        candidate_winding="ccw",
                        candidate_density=180,
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
            return _land(replace(state, boards=boards), plan)
        return state

    if state.stage == "panels":
        if event is Event.LEFT or event is Event.RIGHT:
            delta = -1 if event is Event.LEFT else 1
            nxt = _cycle(state.free_channels(plan), state.candidate_channel, delta)
            return replace(state, candidate_channel=nxt or 0)
        if event is Event.UP:
            return replace(
                state,
                candidate_density=360 if state.candidate_density == 180 else 180,
            )
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
            channels[state.candidate_channel] = ChannelRecord(
                face=panel.face,
                winding=state.candidate_winding,
                density=state.candidate_density,
            )
            boards[unit] = replace(boards[unit], channels=channels)
            return _land(replace(state, boards=boards), plan)

    return state  # done: inert
