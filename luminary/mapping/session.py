"""SessionCore: one place that turns mapping state into running engines.

Two engines, both speaking the wire codec (spec §1.3.1 — no side
channels):

  window — the base station's intent view, rendered on the true net
           capture. Browser mirror pages decode these frames with the
           standard client decoder.
  wire   — what the boards receive, rendered on the *hypothesis*
           geometry.

The two views are an exact broadcast of one scene: `_unit_roles` decides
each board's role once per state (beads / breathe / solid / active test
/ ring), and both builders apply it — the window on the planned panels,
the wire on the strips. Every probed controller is on the wire in every
stage (a deselected board falls back to the beads backdrop instead of
stranding its last frame; before mapping, the beads land scrambled on
the physical build — by design). Placement is the only difference:
recorded channels use their recorded density and winding, everything
else uses the canonical hypothesis (channel j ↔ planned panel j, 360
LEDs, ccw).

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
the true per-LED path stays open under spec §19.6. Wire lights borrow
PHI_S from the nearest net-capture light in their panel, so the mapped
ring broadcasts identically on both surfaces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from luminary.comms.codec import CodecConfig
from luminary.engine.engine import Engine
from luminary.geometry.lights import LightColumns, LightsGeometry, LightSpec, SpaceSpec
from luminary.mapping import render as R
from luminary.mapping.plan import PanelPlan, Plan
from luminary.mapping.state import Event, MappingState, step
from luminary.patterns.base import Pattern

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"

_HYPO_DENSITY = 360  # hypothesis LEDs where a strip's density is unknown
_PREVIEW_LEDS = 30  # unmapped strips on the active board: first-LED preview
_QUARTER = 0.25  # active strip: wheel on first+last quarter, OFF between

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
        hues = R.board_hues(len(plan.units))
        self._unit_hue = {u: float(hues[i]) for i, u in enumerate(plan.units)}
        self._last_t = 0.0  # session clock, anchors the completion finale
        self._show: Optional[Pattern] = None
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

    # ------------------------------------------------ shared assignment

    def _unit_roles(self) -> Dict[int, str]:
        """Every board's surface role for the current state — identical
        on the window and the wire; only placement differs."""
        st, plan = self.state, self.plan
        out: Dict[int, str] = {}
        for i, unit in enumerate(plan.units):
            board = st.boards[unit]
            if st.stage == "done":
                out[unit] = "ring"
            elif st.stage == "ports":
                if i == st.board_cursor and board.controller_id is None:
                    out[unit] = "breathe"
                elif board.controller_id is not None:
                    out[unit] = "solid"
                else:
                    out[unit] = "beads"
            else:  # panels
                if len(board.channels) == len(plan.panels[unit]):
                    out[unit] = "ring"
                elif i == st.board_cursor:
                    out[unit] = "active"
                else:
                    out[unit] = "solid"
        return out

    # ---------------------------------------------------- panel helpers

    def _panel_arc(self, panel: PanelPlan) -> Tuple[float, float, float]:
        """(a0, signed span, strip radius) of a panel's arc about its
        six-red corner (mirrored by web.py's _panel_arcs)."""
        pts = self._net_geometry["points"]
        tris = [t for s in self._net_geometry["triangles"] for t in s]
        tri = tris[panel.tri_index]
        corner = np.asarray(panel.corner_xy)
        others = [
            np.asarray(pts[i][:2]) for i in tri if not np.allclose(pts[i][:2], corner)
        ]
        a0 = float(np.arctan2(*(others[0] - corner)[::-1]))
        a1 = float(np.arctan2(*(others[1] - corner)[::-1]))
        span = float(np.mod(a1 - a0 + np.pi, 2 * np.pi) - np.pi)
        radius = 0.55 * min(float(np.linalg.norm(o - corner)) for o in others)
        return a0, span, radius

    def _arc_frac(self, panel: PanelPlan, xy: np.ndarray) -> np.ndarray:
        """Each position's fraction along the panel's arc from the a0
        edge — the window-side mirror of hypothesis strip index / n."""
        a0, span, _ = self._panel_arc(panel)
        rel = xy - np.asarray(panel.corner_xy)
        ang = np.arctan2(rel[:, 1], rel[:, 0])
        d = np.mod(ang - a0 + np.pi, 2 * np.pi) - np.pi
        frac: np.ndarray = np.clip(d / span, 0.0, 1.0)
        return frac

    def _strip_xy(self, panel: PanelPlan, density: int, winding: str) -> np.ndarray:
        """Angular strip model: n positions arcing about the corner."""
        a0, span, radius = self._panel_arc(panel)
        corner = np.asarray(panel.corner_xy)
        s = (np.arange(density) + 0.5) / density
        if winding == "cw":
            s = s[::-1]
        ang = a0 + span * s
        arc: np.ndarray = corner[None, :] + radius * np.stack(
            [np.cos(ang), np.sin(ang)], axis=1
        )
        return arc

    def _strip_phi(self, panel: PanelPlan, xy: np.ndarray) -> np.ndarray:
        """PHI_S per strip light: nearest net-capture light in the same
        panel (exact to LED pitch — plenty for the ring's 6° sigma)."""
        m = self._net_tri == panel.tri_index
        pts = self._net_xy[m]
        phis = self._net_phi[m]
        d = ((xy[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        return np.asarray(phis[d.argmin(axis=1)])

    # ----------------------------------------------------------- window

    def _window_roles(self) -> Dict[str, np.ndarray]:
        n = self._net_xy.shape[0]
        roles = np.full(n, R.BEADS, dtype=np.int64)
        corner = np.zeros((n, 2))
        hue = np.zeros(n)
        st, plan = self.state, self.plan
        unit_roles = self._unit_roles()
        constant = {
            "beads": R.BEADS,
            "breathe": R.BREATHE,
            "solid": R.SOLID,
            "ring": R.RING,
        }

        for i, unit in enumerate(plan.units):
            board = st.boards[unit]
            for j, p in enumerate(plan.panels[unit]):
                m = self._net_tri == p.tri_index
                corner[m] = p.corner_xy
                hue[m] = self._unit_hue[unit]
                role = unit_roles[unit]
                if role != "active":
                    roles[m] = constant[role]
                    continue
                recorded = any(rec.face == p.face for rec in board.channels.values())
                frac = self._arc_frac(p, self._net_xy[m])
                if j == st.panel_cursor:
                    # The strip under test: wheel on the first and last
                    # quarters, deliberately dark between — a density
                    # mismatch reads as only one half of the strip lit.
                    ends = (frac <= _QUARTER) | (frac >= 1.0 - _QUARTER)
                    roles[m] = np.where(ends, R.WHEEL_FULL, R.OFF)
                elif recorded:
                    roles[m] = R.WHEEL_DIM
                else:
                    # Waiting panel: the first-30-LED preview sliver of
                    # its intended wheel portion, dimmed like recorded strips.
                    sliver = frac <= _PREVIEW_LEDS / _HYPO_DENSITY
                    roles[m] = np.where(sliver, R.WHEEL_DIM, R.BEADS)
        return {"roles": roles, "corner": corner, "hue": hue}

    def _window_pattern(self) -> R.MappingPattern:
        parts = self._window_roles()
        return R.MappingPattern(
            xy=self._net_xy,
            roles=parts["roles"],
            edges=self._edges,
            corner_xy=parts["corner"],
            hue=parts["hue"],
            phi_s=self._net_phi,
        )

    # ------------------------------------------------------------- wire

    def _controller_units(self) -> Dict[int, int]:
        """controller id -> the unit whose scene it plays. Locked boards
        keep their id; the ports-stage candidate carries the cursor
        board; every remaining probed controller is paired provisionally
        (plan order) so it keeps receiving frames — deselecting a board
        cleans it up to beads instead of stranding its last color."""
        st, plan = self.state, self.plan
        pair: Dict[int, int] = {}
        for unit in plan.units:
            cid = st.boards[unit].controller_id
            if cid is not None:
                pair[cid] = unit
        if st.stage == "ports" and st.candidate_controller is not None:
            pair[st.candidate_controller] = plan.units[st.board_cursor]
        taken = set(pair.values())
        leftover = [u for u in plan.units if u not in taken]
        spare = [c for c in st.controllers if c not in pair]
        for k, cid in enumerate(spare):
            pool = leftover or plan.units
            pair[cid] = pool[k % len(pool)]
        return pair

    def _wire_build(self) -> Optional[LightsGeometry]:
        st, plan = self.state, self.plan
        unit_roles = self._unit_roles()
        specs: List[LightSpec] = []
        role_parts: List[np.ndarray] = []
        corner_parts: List[np.ndarray] = []
        hue_parts: List[np.ndarray] = []
        phi_parts: List[np.ndarray] = []

        def add_strip(
            controller: int,
            channel: int,
            xy: np.ndarray,
            role: Union[int, np.ndarray],
            panel: PanelPlan,
        ) -> None:
            n = xy.shape[0]
            for i in range(n):
                specs.append(
                    LightSpec(
                        controller=controller,
                        channel=channel,
                        index=i,
                        kind="active",
                        pos=[float(xy[i, 0]), float(xy[i, 1])],
                    )
                )
            role_parts.append(
                np.full(n, role, dtype=np.int64)
                if np.isscalar(role)
                else np.asarray(role, dtype=np.int64)
            )
            corner_parts.append(np.tile(np.asarray(panel.corner_xy), (n, 1)))
            hue_parts.append(np.full(n, self._unit_hue[panel.unit_vertex]))
            phi_parts.append(self._strip_phi(panel, xy))

        for cid, unit in sorted(self._controller_units().items()):
            board = st.boards[unit]
            role = unit_roles[unit]
            panels = plan.panels[unit]

            if role == "ring":
                for ch, rec in board.channels.items():
                    p = plan.by_face[rec.face]
                    add_strip(
                        cid, ch, self._strip_xy(p, rec.density, rec.winding), R.RING, p
                    )
                continue

            if role == "active":
                for ch, rec in board.channels.items():
                    p = plan.by_face[rec.face]
                    add_strip(
                        cid,
                        ch,
                        self._strip_xy(p, rec.density, rec.winding),
                        R.WHEEL_DIM,
                        p,
                    )
                cursor_panel = panels[st.panel_cursor]
                xy = self._strip_xy(
                    cursor_panel, st.candidate_density, st.candidate_winding
                )
                idx = np.arange(xy.shape[0])
                quarter = int(xy.shape[0] * _QUARTER)
                ends = (idx < quarter) | (idx >= xy.shape[0] - quarter)
                add_strip(
                    cid,
                    st.candidate_channel,
                    xy,
                    np.where(ends, R.WHEEL_FULL, R.OFF),
                    cursor_panel,
                )
                recorded_faces = {rec.face for rec in board.channels.values()}
                waiting = [
                    p
                    for j, p in enumerate(panels)
                    if p.face not in recorded_faces and j != st.panel_cursor
                ]
                free = [
                    ch
                    for ch in range(8)
                    if ch not in board.channels and ch != st.candidate_channel
                ]
                for k, ch in enumerate(free):
                    if k < len(waiting):
                        p = waiting[k]
                        xy = self._strip_xy(p, _HYPO_DENSITY, "ccw")
                        preview = np.where(
                            np.arange(_HYPO_DENSITY) < _PREVIEW_LEDS,
                            R.WHEEL_DIM,
                            R.BEADS,
                        )
                        add_strip(cid, ch, xy, preview, p)
                    else:
                        p = panels[k % len(panels)]
                        add_strip(
                            cid, ch, self._strip_xy(p, _HYPO_DENSITY, "ccw"), R.BEADS, p
                        )
                continue

            # beads / breathe / solid: all 8 channels stay fed —
            # whatever is physically plugged follows the board's scene.
            # Recorded channels (a paused board) keep their true
            # placement; the rest take the canonical hypothesis.
            constant = {"beads": R.BEADS, "breathe": R.BREATHE, "solid": R.SOLID}[role]
            for ch in range(8):
                known = board.channels.get(ch)
                if known is not None:
                    p = plan.by_face[known.face]
                    xy = self._strip_xy(p, known.density, known.winding)
                else:
                    p = panels[ch % len(panels)]
                    xy = self._strip_xy(p, _HYPO_DENSITY, "ccw")
                add_strip(cid, ch, xy, constant, p)

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
        self._wire_roles = np.concatenate(role_parts)[order]
        self._wire_corner = np.concatenate(corner_parts)[order]
        self._wire_hue = np.concatenate(hue_parts)[order]
        self._wire_phi = np.concatenate(phi_parts)[order]
        return lights

    def _wire_pattern(self, lights: LightsGeometry) -> R.MappingPattern:
        xy = lights.array[:, [LightColumns.X, LightColumns.Y]]
        return R.MappingPattern(
            xy=xy,
            roles=self._wire_roles,
            edges=self._edges,
            corner_xy=self._wire_corner,
            hue=self._wire_hue,
            phi_s=self._wire_phi,
        )

    # -------------------------------------------------------- lifecycle

    def _show_pattern(self) -> Pattern:
        """The post-mapping show (`spiral`, from the repo's patterns)."""
        if self._show is None:
            from luminary.patterns.registry import default_registry

            self._show = default_registry().get("spiral")
        return self._show

    def rebuild(self) -> None:
        done = self.state.stage == "done"
        window_pattern: Pattern = (
            R.FinalePattern(
                self._show_pattern(),
                self._net_xy,
                self._net_phi,
                self._edges,
                self._last_t,
            )
            if done
            else self._window_pattern()
        )
        self.window_engine = Engine(self._net_lights, window_pattern, fps=self.fps)
        wire_lights = self._wire_build()
        if wire_lights is None:
            self.wire_engine = None
            return
        wire_pattern: Pattern
        if done:
            xy = wire_lights.array[:, [LightColumns.X, LightColumns.Y]]
            wire_pattern = R.FinalePattern(
                self._show_pattern(), xy, self._wire_phi, self._edges, self._last_t
            )
        else:
            wire_pattern = self._wire_pattern(wire_lights)
        self.wire_engine = Engine(
            wire_lights,
            wire_pattern,
            fps=self.fps,
            codec_config=CodecConfig(),
        )

    def session_frames(self) -> Dict[str, List[bytes]]:
        out: Dict[str, List[bytes]] = {"window": [], "wire": []}
        if self.window_engine is not None:
            out["window"] = list(self.window_engine.session_frames())
        if self.wire_engine is not None:
            out["wire"] = list(self.wire_engine.session_frames())
        return out

    def tick(self, t: float) -> None:
        self._last_t = t  # the finale anchors to the completion moment
        if self.window_engine is not None:
            frames = self.window_engine.frame(t)
            for sink in self.window_sinks:
                sink(frames)
        if self.wire_engine is not None:
            frames = self.wire_engine.frame(t)
            for sink in self.wire_sinks:
                sink(frames)
