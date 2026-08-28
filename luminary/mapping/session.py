"""SessionCore: one place that turns mapping state into running engines.

Two engines, both speaking the wire codec (spec §1.3.1 — no side
channels):

  window — the base station's intent view, rendered on the true net
           capture. Browser mirror pages decode these frames with the
           standard client decoder.
  wire   — what the boards receive, rendered on the *hypothesis*
           geometry.

The two views are an exact broadcast of one scene, twice over. First,
`_unit_roles` decides each board's role once per state (beads / breathe
/ solid / active test / ring), and both builders apply it — the window
on the planned panels, the wire on the strips. Second, every rendered
light carries a **reference net light** (`ref`): the wire's fields are
never evaluated at hypothesis positions — render.MappingPattern
computes every positional field on the net capture only and gathers it
through `ref`, so the surfaces cannot diverge (the hypothesis changes
which net lights a strip's indices reference, never the field values).
Every probed controller is on the wire in every stage (a deselected
board falls back to the beads backdrop instead of stranding its last
frame; before mapping, the beads land scrambled on the physical build —
by design). Recorded channels use their recorded density and winding;
everything else uses the canonical hypothesis (channel j ↔ planned
panel j, 360 LEDs, ccw).

Adapters register frame sinks (serial writers, WebSocket broadcasters)
and feed key events in; the core owns state transitions, engine
rebuilds, and the SESSION resync that must follow every rebuild
(``resync_sinks`` — sent to every registered sink by the core itself,
so no adapter can forget it or implement it differently). Adapters'
state hooks are left with genuinely adapter-local work: persistence,
HUD pushes, redraws. A late joiner gets its SESSION from its own
connection handler; a rebuild and a late join are then the same clean
resync.

Strip model: the physical serpentine (plan/mapping/DESCRIPTION.md).
From the six-red start corner the strip runs half-way down the first
edge, in along that radial to the center and back out its other side,
finishes the edge; then the same along the far edge and the third,
returning to the start corner. LED i of n sits at arclength
(i + 0.5)/n along that 12-leg path; a cw winding walks the same path
the other way. Each hypothesis LED's `ref` is the nearest capture
light in its panel — the capture's beams run along the same legs, so
the reference is tight.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from luminary.comms.codec import CodecConfig
from luminary.engine.engine import Engine
from luminary.geometry.lights import LightColumns, LightsGeometry, LightSpec, SpaceSpec
from luminary.mapping import render as R
from luminary.mapping.plan import PanelPlan, Plan
from luminary.mapping.state import Event, MappingState, step
from luminary.mapping.strip_path import StripPaths, tri_of_lights
from luminary.patterns.base import Pattern

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"

_HYPO_DENSITY = 360  # hypothesis LEDs where a strip's density is unknown
_PREVIEW_LEDS = 30  # unmapped strips on the active board: first-LED preview
_QUARTER = 0.25  # active strip: wheel on first+last quarter, OFF between

# Scene name -> constant role, for every non-"active" scene.
_CONSTANT_ROLE = {
    "beads": R.BEADS,
    "breathe": R.BREATHE,
    "solid": R.SOLID,
    "ring": R.RING,
}

FrameSink = Callable[[List[bytes]], None]


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
        self._strips = StripPaths(self._net_geometry, xy)
        self._net_tri = self._strips.net_tri
        self._net_phi = net_lights.array[:, LightColumns.PHI_S]
        hues = R.board_hues(len(plan.units))
        self._unit_hue = {u: float(hues[i]) for i, u in enumerate(plan.units)}
        # The wheel anchors at each board's HOME vertex: the corner its
        # panels meet at (the most common six-red corner among them) —
        # a consolidated board's panels all share their corner (unit
        # 45's three meet at vertex 34), and a hexagon board's corner
        # is its own vertex. Panels whose corner differs (the data-aux
        # door faces) continue their board's wheel rather than starting
        # their own. The strip path still starts at each panel's corner.
        anchor_xy: Dict[int, Tuple[float, float]] = {}
        for unit, plist in plan.panels.items():
            counts = Counter(p.corner_vertex for p in plist)
            home = min(counts, key=lambda v: (-counts[v], v))
            anchor_xy[unit] = next(
                p.corner_xy for p in plist if p.corner_vertex == home
            )
        nb = xy.shape[0]
        self._net_anchor = np.zeros((nb, 2))
        self._net_hue = np.zeros(nb)
        for p in (p for plist in plan.panels.values() for p in plist):
            m = self._net_tri == p.tri_index
            self._net_anchor[m] = anchor_xy[p.unit_vertex]
            self._net_hue[m] = self._unit_hue[p.unit_vertex]
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
            self.reset_state(new)
        return new

    def reset_state(self, state: MappingState) -> None:
        """Adopt a whole new state — the demo's start-over, or any other
        wholesale replacement — with the same rebuild, SESSION resync,
        and change hooks a stepped transition gets."""
        self.state = state
        self.rebuild()
        self.resync_sinks()
        for hook in self.on_state_change:
            hook(state)

    def resync_sinks(self) -> None:
        """Fresh SESSION frames to every registered sink — the rebuild
        resync contract, owned by the core so no adapter can forget it
        or implement it differently. (A topology-changing rebuild
        without a fresh SESSION would mis-size firmware strips; the
        rebuilt engines keyframe on their next tick.)"""
        frames = self.session_frames()
        for sink in list(self.window_sinks):
            sink(frames["window"])
        for sink in list(self.wire_sinks):
            sink(frames["wire"])

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
                    # Stage-A identity colors did their job; boards
                    # waiting their stage-B turn return to the beads
                    # backdrop (still scrambled strip/density-wise).
                    out[unit] = "beads"
        return out

    # ------------------------------------------- the serpentine path

    def _panel_path(self, panel: PanelPlan) -> Tuple[np.ndarray, np.ndarray]:
        """Delegates to :class:`~luminary.mapping.strip_path.StripPaths` —
        the one implementation, shared with the production capture."""
        return self._strips.panel_path(panel)

    def _strip_path_xy(
        self, panel: PanelPlan, density: int, winding: str
    ) -> np.ndarray:
        """Delegates to :class:`~luminary.mapping.strip_path.StripPaths` —
        the one implementation, shared with the production capture."""
        return self._strips.strip_xy(panel, density, winding)

    def strip_refs(self, panel: PanelPlan, density: int, winding: str) -> np.ndarray:
        """Delegates to :class:`~luminary.mapping.strip_path.StripPaths` —
        the one implementation, shared with the production capture."""
        return self._strips.strip_refs(panel, density, winding)

    def _panel_path_frac(self, panel: PanelPlan) -> Tuple[np.ndarray, np.ndarray]:
        """Delegates to :class:`~luminary.mapping.strip_path.StripPaths` —
        the one implementation, shared with the production capture."""
        return self._strips.panel_path_frac(panel)

    def _strip_roles(
        self,
        scene: str,
        panel: PanelPlan,
        is_cursor: bool,
        frac: np.ndarray,
    ) -> np.ndarray:
        """THE per-light role rule, in terms of each light's fraction
        along the panel's strip path. The window calls it with its
        capture lights' path fractions, the wire with strip index
        fractions ((i + 0.5) / n): the decision logic exists exactly
        once — surfaces differ only in where their lights sit.

        Cursor strip: wheel on the first and last quarters of the path,
        deliberately dark between (a density mismatch reads as only one
        half of the strip lit). Recorded panel: the dim wheel. Waiting
        panel: the first-30-LED preview sliver, dimmed like recorded.
        Every other scene is one constant role.
        """
        n = frac.shape[0]
        if scene != "active":
            return np.full(n, _CONSTANT_ROLE[scene], dtype=np.int64)
        if is_cursor:
            ends = (frac <= _QUARTER) | (frac >= 1.0 - _QUARTER)
            return np.asarray(np.where(ends, R.WHEEL_FULL, R.OFF))
        board = self.state.boards[panel.unit_vertex]
        if any(rec.face == panel.face for rec in board.channels.values()):
            return np.full(n, R.WHEEL_DIM, dtype=np.int64)
        sliver = frac <= _PREVIEW_LEDS / _HYPO_DENSITY
        return np.asarray(np.where(sliver, R.WHEEL_DIM, R.BEADS))

    # ----------------------------------------------------------- window

    def _window_roles(self) -> np.ndarray:
        n = self._net_xy.shape[0]
        roles = np.full(n, R.BEADS, dtype=np.int64)
        st, plan = self.state, self.plan
        unit_roles = self._unit_roles()
        for unit in plan.units:
            scene = unit_roles[unit]
            for j, p in enumerate(plan.panels[unit]):
                idx, frac = self._panel_path_frac(p)
                is_cursor = scene == "active" and j == st.panel_cursor
                roles[idx] = self._strip_roles(scene, p, is_cursor, frac)
        return roles

    def _window_pattern(self) -> R.MappingPattern:
        return R.MappingPattern(
            roles=self._window_roles(),
            ref=np.arange(self._net_xy.shape[0]),
            net_xy=self._net_xy,
            edges=self._edges,
            net_anchor=self._net_anchor,
            net_hue=self._net_hue,
            net_phi=self._net_phi,
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
        ref_parts: List[np.ndarray] = []

        def add_strip(
            controller: int,
            channel: int,
            panel: PanelPlan,
            density: int,
            winding: str,
            scene: str,
            is_cursor: bool = False,
        ) -> None:
            xy = self._strip_path_xy(panel, density, winding)
            for i in range(density):
                specs.append(
                    LightSpec(
                        controller=controller,
                        channel=channel,
                        index=i,
                        kind="active",
                        pos=[float(xy[i, 0]), float(xy[i, 1])],
                    )
                )
            frac = (np.arange(density) + 0.5) / density
            role_parts.append(self._strip_roles(scene, panel, is_cursor, frac))
            ref_parts.append(self.strip_refs(panel, density, winding))

        for cid, unit in sorted(self._controller_units().items()):
            board = st.boards[unit]
            scene = unit_roles[unit]
            panels = plan.panels[unit]

            if scene == "ring":
                for ch, rec in board.channels.items():
                    p = plan.by_face[rec.face]
                    add_strip(cid, ch, p, rec.density, rec.winding, "ring")
                continue

            if scene == "active":
                for ch, rec in board.channels.items():
                    p = plan.by_face[rec.face]
                    add_strip(cid, ch, p, rec.density, rec.winding, "active")
                add_strip(
                    cid,
                    st.candidate_channel,
                    panels[st.panel_cursor],
                    st.candidate_density,
                    st.candidate_winding,
                    "active",
                    is_cursor=True,
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
                        add_strip(cid, ch, waiting[k], _HYPO_DENSITY, "ccw", "active")
                    else:
                        p = panels[k % len(panels)]
                        add_strip(cid, ch, p, _HYPO_DENSITY, "ccw", "beads")
                continue

            # beads / breathe / solid: all 8 channels stay fed —
            # whatever is physically plugged follows the board's scene.
            # Recorded channels (a paused board) keep their true
            # placement; the rest take the canonical hypothesis.
            for ch in range(8):
                known = board.channels.get(ch)
                if known is not None:
                    p = plan.by_face[known.face]
                    add_strip(cid, ch, p, known.density, known.winding, scene)
                else:
                    p = panels[ch % len(panels)]
                    add_strip(cid, ch, p, _HYPO_DENSITY, "ccw", scene)

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
        self._wire_ref = np.concatenate(ref_parts)[order]
        return lights

    def _wire_pattern(self, lights: LightsGeometry) -> R.MappingPattern:
        return R.MappingPattern(
            roles=self._wire_roles,
            ref=self._wire_ref,
            net_xy=self._net_xy,
            edges=self._edges,
            net_anchor=self._net_anchor,
            net_hue=self._net_hue,
            net_phi=self._net_phi,
        )

    # -------------------------------------------------------- lifecycle

    def _show_pattern(self) -> Pattern:
        """The post-mapping show (`spiral`, from the repo's patterns)."""
        if self._show is None:
            from luminary.patterns.registry import default_registry

            self._show = default_registry().get("spiral")
        return self._show

    def _finale(self, ref: np.ndarray) -> R.FinalePattern:
        return R.FinalePattern(
            show=self._show_pattern(),
            net_lights=self._net_lights.array,
            net_xy=self._net_xy,
            net_phi=self._net_phi,
            edges=self._edges,
            ref=ref,
            t0=self._last_t,
        )

    def rebuild(self) -> None:
        done = self.state.stage == "done"
        window_pattern: Pattern = (
            self._finale(np.arange(self._net_xy.shape[0]))
            if done
            else self._window_pattern()
        )
        self.window_engine = Engine(self._net_lights, window_pattern, fps=self.fps)
        wire_lights = self._wire_build()
        if wire_lights is None:
            self.wire_engine = None
            return
        wire_pattern: Pattern = (
            self._finale(self._wire_ref) if done else self._wire_pattern(wire_lights)
        )
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
