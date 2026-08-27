"""SessionCore: one place that turns mapping state into running engines.

Two engines, both speaking the wire codec (spec §1.3.1 — no side
channels):

  window — the base station's intent view, rendered on the true net
           capture. Browser mirror pages decode these frames with the
           standard client decoder.
  wire   — what the boards receive, rendered on the *hypothesis*
           geometry: recorded channels at their recorded density and
           winding, the live candidate under test, and whole-board
           breathing during the ports stage.

Adapters register frame sinks (serial writers, WebSocket broadcasters)
and feed key events in; the core owns state transitions and engine
rebuilds. A rebuild constructs fresh Engine instances, whose first tick
emits a keyframe; **re-sending SESSION frames after a rebuild is the
adapter's job** (both the TUI and the web app do this from their state
hooks — a topology-changing rebuild without a fresh SESSION would
mis-size firmware strips). Late joiners and hypothesis changes are then
the same case.

Strip model note: within a panel the wire positions use the angular
strip model — LED index i of n maps to the arc about the panel's
six-red corner (winding-signed) at interior radius. This is an
approximation of the physical serpentine that is exact in the two facts
the wheel test verifies (sweep direction and arc coverage / density);
the true per-LED path stays open under spec §19.6.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from luminary.comms.codec import CodecConfig
from luminary.engine.engine import Engine
from luminary.geometry.lights import LightColumns, LightsGeometry, LightSpec, SpaceSpec
from luminary.mapping import render as R
from luminary.mapping.plan import PanelPlan, Plan
from luminary.mapping.state import Event, MappingState, step

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"

FrameSink = Callable[[List[bytes]], None]


def _tri_of_lights(net_geometry: dict, xy: np.ndarray) -> np.ndarray:
    """(n,) triangle index per light by point location (capture order is
    not triangle-contiguous after the canonical identity sort)."""
    pts = net_geometry["points"]
    tris = [t for series in net_geometry["triangles"] for t in series]
    out = np.full(xy.shape[0], -1, dtype=np.int64)
    for idx, tri in enumerate(tris):
        (x0, y0), (x1, y1), (x2, y2) = ((pts[i][0], pts[i][1]) for i in tri)
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        l0 = ((y1 - y2) * (xy[:, 0] - x2) + (x2 - x1) * (xy[:, 1] - y2)) / det
        l1 = ((y2 - y0) * (xy[:, 0] - x2) + (x0 - x2) * (xy[:, 1] - y2)) / det
        l2 = 1.0 - l0 - l1
        inside = (l0 > -1e-6) & (l1 > -1e-6) & (l2 > -1e-6) & (out < 0)
        out[inside] = idx
    assert (out >= 0).all(), "unlocated lights"
    return out


class SessionCore:
    def __init__(
        self,
        plan: Plan,
        net_lights: LightsGeometry,
        state: MappingState,
        fps: float = 30.0,
    ) -> None:
        self.plan = plan
        self.state = state
        self.fps = fps
        self._net_lights = net_lights
        self._net_geometry = json.loads(
            (_CONFIGS / f"{plan.net_name}.json").read_text()
        )["geometry"]
        self._edges = R.net_edges(self._net_geometry)
        xy = net_lights.array[:, [LightColumns.X, LightColumns.Y]]
        self._net_xy = xy
        self._net_tri = _tri_of_lights(self._net_geometry, xy)
        self._net_phi = net_lights.array[:, LightColumns.PHI_S]
        self.window_sinks: List[FrameSink] = []
        self.wire_sinks: List[FrameSink] = []
        self.on_state_change: List[Callable[[MappingState], None]] = []
        self.window_engine: Optional[Engine] = None
        self.wire_engine: Optional[Engine] = None
        self.rebuild()

    # ------------------------------------------------------------ state

    def apply(self, event: Event) -> MappingState:
        new = step(self.state, self.plan, event)
        if new is not self.state:
            self.state = new
            self.rebuild()
            for hook in self.on_state_change:
                hook(new)
        return new

    # ----------------------------------------------------------- window

    def _window_roles(self) -> Dict[str, np.ndarray]:
        n = self._net_xy.shape[0]
        roles = np.full(n, R.BEADS, dtype=np.int64)
        corner = np.zeros((n, 2))
        wind = np.ones(n)
        st, plan = self.state, self.plan

        def tris_of(panels: Sequence[PanelPlan]) -> List[int]:
            return [p.tri_index for p in panels]

        by_tri = {p.tri_index: p for plist in plan.panels.values() for p in plist}
        for t_idx, p in by_tri.items():
            m = self._net_tri == t_idx
            corner[m] = p.corner_xy

        if st.stage == "ports":
            for i, unit in enumerate(plan.units):
                assigned = st.boards[unit].controller_id is not None
                role = (
                    R.BREATHE_FULL
                    if i == st.board_cursor and not assigned
                    else (R.BREATHE_HALF if assigned else R.BEADS)
                )
                for t_idx in tris_of(plan.panels[unit]):
                    roles[self._net_tri == t_idx] = role
        elif st.stage == "panels":
            for i, unit in enumerate(plan.units):
                board = st.boards[unit]
                complete = len(board.channels) == len(plan.panels[unit])
                for j, p in enumerate(plan.panels[unit]):
                    m = self._net_tri == p.tri_index
                    recorded = any(
                        rec.face == p.face for rec in board.channels.values()
                    )
                    if complete:
                        roles[m] = R.RING
                    elif i == st.board_cursor and j == st.panel_cursor:
                        roles[m] = R.WHEEL_FULL
                        wind[m] = 1.0 if st.candidate_winding == "ccw" else -1.0
                    elif recorded:
                        roles[m] = R.WHEEL_HALF
                        rec = next(
                            r for r in board.channels.values() if r.face == p.face
                        )
                        wind[m] = 1.0 if rec.winding == "ccw" else -1.0
        else:  # done
            roles[:] = R.RING
        return {"roles": roles, "corner": corner, "wind": wind}

    def _window_pattern(self) -> R.MappingPattern:
        parts = self._window_roles()
        return R.MappingPattern(
            xy=self._net_xy,
            roles=parts["roles"],
            edges=self._edges,
            corner_xy=parts["corner"],
            winding_sign=parts["wind"],
            phi_s=self._net_phi,
        )

    # ------------------------------------------------------------- wire

    def _strip_xy(self, panel: PanelPlan, density: int, winding: str) -> np.ndarray:
        """Angular strip model: n positions arcing about the corner."""
        pts = self._net_geometry["points"]
        tris = [t for s in self._net_geometry["triangles"] for t in s]
        tri = tris[panel.tri_index]
        corner = np.asarray(panel.corner_xy)
        others = [
            np.asarray(pts[i][:2]) for i in tri if not np.allclose(pts[i][:2], corner)
        ]
        a0 = np.arctan2(*(others[0] - corner)[::-1])
        a1 = np.arctan2(*(others[1] - corner)[::-1])
        span = np.mod(a1 - a0 + np.pi, 2 * np.pi) - np.pi
        s = (np.arange(density) + 0.5) / density
        if winding == "cw":
            s = s[::-1]
        ang = a0 + span * s
        radius = 0.55 * min(np.linalg.norm(o - corner) for o in others)
        arc: np.ndarray = corner[None, :] + radius * np.stack(
            [np.cos(ang), np.sin(ang)], axis=1
        )
        return arc

    def _wire_build(self) -> Optional[LightsGeometry]:
        """Hypothesis geometry: only boards with a locked controller id."""
        st, plan = self.state, self.plan
        specs: List[LightSpec] = []
        meta_roles: List[int] = []
        corners: List[np.ndarray] = []
        winds: List[float] = []

        def add_strip(
            controller: int,
            channel: int,
            xy: np.ndarray,
            role: int,
            corner: np.ndarray,
            wind: float,
        ) -> None:
            for i in range(xy.shape[0]):
                specs.append(
                    LightSpec(
                        controller=controller,
                        channel=channel,
                        index=i,
                        kind="active",
                        pos=[float(xy[i, 0]), float(xy[i, 1])],
                    )
                )
                meta_roles.append(role)
                corners.append(corner)
                winds.append(wind)

        for i, unit in enumerate(plan.units):
            board = st.boards[unit]
            if board.controller_id is None:
                continue
            complete = st.stage != "ports" and len(board.channels) == len(
                plan.panels[unit]
            )
            if st.stage == "ports":
                # Whole-board breathing: all 8 channels at full density —
                # covers either physical density, extra indexes are inert.
                centroid = np.mean([p.corner_xy for p in plan.panels[unit]], axis=0)
                role = R.BREATHE_HALF
                xy = np.tile(centroid, (360, 1))
                for ch in range(8):
                    add_strip(board.controller_id, ch, xy, role, centroid, 1.0)
                continue
            for ch, rec in board.channels.items():
                p = plan.by_face[rec.face]
                xy = self._strip_xy(p, rec.density, rec.winding)
                role = R.RING if complete else R.WHEEL_HALF
                add_strip(
                    board.controller_id,
                    ch,
                    xy,
                    role,
                    np.asarray(p.corner_xy),
                    1.0 if rec.winding == "ccw" else -1.0,
                )
            if st.stage == "panels" and plan.units[st.board_cursor] == unit:
                p = plan.panels[unit][st.panel_cursor]
                xy = self._strip_xy(p, st.candidate_density, st.candidate_winding)
                add_strip(
                    board.controller_id,
                    st.candidate_channel,
                    xy,
                    R.WHEEL_FULL,
                    np.asarray(p.corner_xy),
                    1.0 if st.candidate_winding == "ccw" else -1.0,
                )

        # The ports stage also breathes the *candidate* board at full.
        if st.stage == "ports" and st.candidate_controller is not None:
            unit = plan.units[st.board_cursor]
            centroid = np.mean([p.corner_xy for p in plan.panels[unit]], axis=0)
            xy = np.tile(centroid, (360, 1))
            for ch in range(8):
                add_strip(
                    st.candidate_controller, ch, xy, R.BREATHE_FULL, centroid, 1.0
                )

        if not specs:
            return None
        lights = LightsGeometry.from_specs(
            specs,
            space=SpaceSpec(authoritative=["xy"]),
            source={"type": "mapping-hypothesis"},
            meta={"name": "mapping-wire"},
        )
        # Reattach per-row annotations in canonical order.
        order = np.lexsort(
            (
                [s.index for s in specs],
                [s.channel for s in specs],
                [s.controller for s in specs],
            )
        )
        self._wire_roles = np.asarray(meta_roles)[order]
        self._wire_corner = np.asarray(corners)[order]
        self._wire_wind = np.asarray(winds)[order]
        return lights

    def _wire_pattern(self, lights: LightsGeometry) -> R.MappingPattern:
        xy = lights.array[:, [LightColumns.X, LightColumns.Y]]
        return R.MappingPattern(
            xy=xy,
            roles=self._wire_roles,
            edges=self._edges,
            corner_xy=self._wire_corner,
            winding_sign=self._wire_wind,
            phi_s=None,
        )

    # -------------------------------------------------------- lifecycle

    def rebuild(self) -> None:
        self.window_engine = Engine(
            self._net_lights, self._window_pattern(), fps=self.fps
        )
        wire_lights = self._wire_build()
        self.wire_engine = (
            Engine(
                wire_lights,
                self._wire_pattern(wire_lights),
                fps=self.fps,
                codec_config=CodecConfig(),
            )
            if wire_lights is not None
            else None
        )

    def session_frames(self) -> Dict[str, List[bytes]]:
        out: Dict[str, List[bytes]] = {"window": [], "wire": []}
        if self.window_engine is not None:
            out["window"] = list(self.window_engine.session_frames())
        if self.wire_engine is not None:
            out["wire"] = list(self.wire_engine.session_frames())
        return out

    def tick(self, t: float) -> None:
        if self.window_engine is not None:
            frames = self.window_engine.frame(t)
            for sink in self.window_sinks:
                sink(frames)
        if self.wire_engine is not None:
            frames = self.wire_engine.frame(t)
            for sink in self.wire_sinks:
                sink(frames)
