"""The deployment plan, derived from configs — nothing here is guessed.

Every plan-A panel face is B-C-C, so it has exactly one corner where its
two C (red) struts meet: the six-red hexagon-center vertex. That corner
is (a) the physical strip's start corner — always, by build convention —
and (b) the key that assigns the face to its data unit: the unit at that
vertex, or the consolidation chip that serves it (sphere3v
`electronics.data_consolidations`).

The production default is the data-aux wiring (sphere3v
`electronics.data_aux`, the construction app's aux mode "data"): the
front hexagon unit keeps power but its three door-side hairband panels
hand their data to the flanking hexagon boards — two ride the screen-
right flank, one the left — so the front unit fields no data board at
all. The strip start corner is unchanged (it is a physical property of
the panel); only which board drives it moves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"

Face = Tuple[int, int, int]  # sorted sphere3v vertex ids


@dataclass(frozen=True)
class PanelPlan:
    face: Face
    unit_vertex: int  # the data unit that serves this panel
    corner_vertex: int  # the six-red start corner (C-C meeting point)
    tri_index: int  # index into the net's flattened triangle list
    corner_xy: Tuple[float, float]  # the corner's net-plane position


@dataclass(frozen=True)
class Plan:
    """Boards (data units) and the panels each serves, in mapping order."""

    units: List[int]  # data-unit vertices, mapping order
    panels: Dict[int, List[PanelPlan]]  # unit vertex -> its panels
    by_face: Dict[Face, PanelPlan] = field(repr=False)
    net_name: str = "4A-33"
    data_aux: bool = True

    @property
    def n_panels(self) -> int:
        return sum(len(p) for p in self.panels.values())

    @classmethod
    def load(cls, net_name: str = "4A-33", data_aux: bool = True) -> "Plan":
        sphere = json.loads((_CONFIGS / "sphere3v.json").read_text())
        net = json.loads((_CONFIGS / f"{net_name}.json").read_text())
        g = net["geometry"]

        class_of: Dict[Tuple[int, int], str] = {}
        for i, j, c in sphere["edges"]:
            class_of[(min(i, j), max(i, j))] = c

        elec = sphere["electronics"]
        unit_of: Dict[int, int] = {v: v for v in elec["data_unit_vertices"]}
        for chip, served in elec["data_consolidations"].items():
            for v in served:
                unit_of[v] = int(chip)
        aux_of: Dict[Tuple[int, ...], int] = {}
        if data_aux:
            for f, u in elec["data_aux"]["reassign"]:
                aux_of[tuple(sorted(f))] = int(u)

        point_vertex: List[Optional[int]] = g["fold"]["point_vertex"]
        tris: List[Tuple[int, int, int]] = [
            tuple(t) for series in g["triangles"] for t in series
        ]

        panels: Dict[int, List[PanelPlan]] = {v: [] for v in elec["data_unit_vertices"]}
        by_face: Dict[Face, PanelPlan] = {}
        for tri_index, tri in enumerate(tris):
            verts: List[int] = []
            for p in tri:
                v = point_vertex[p]
                assert v is not None
                verts.append(v)
            face: Face = tuple(sorted(verts))  # type: ignore[assignment]
            # The six-red corner: the vertex incident to both C edges.
            corner = None
            for k in range(3):
                a, b = verts[k], verts[(k + 1) % 3]
                c = verts[(k + 2) % 3]
                e1 = class_of[(min(a, c), max(a, c))]
                e2 = class_of[(min(b, c), max(b, c))]
                if e1 == "C" and e2 == "C":
                    corner = c
                    corner_point = tri[(k + 2) % 3]
            assert corner is not None, f"face {face} has no C-C corner"
            unit = aux_of.get(face, unit_of[corner])
            px, py = g["points"][corner_point][0], g["points"][corner_point][1]
            plan = PanelPlan(
                face=face,
                unit_vertex=unit,
                corner_vertex=corner,
                tri_index=tri_index,
                corner_xy=(px, py),
            )
            panels[unit].append(plan)
            by_face[face] = plan

        # A unit with no panels fields no board (data-aux empties the
        # front unit — its panels ride the flanks).
        panels = {v: plist for v, plist in panels.items() if plist}
        for unit, plist in panels.items():
            assert 0 < len(plist) <= 8, f"unit {unit} serves {len(plist)} panels"
            # Mapping order within a board: stable by triangle index.
            plist.sort(key=lambda p: p.tri_index)

        units = sorted(panels, key=lambda v: min(p.tri_index for p in panels[v]))
        return cls(
            units=units,
            panels=panels,
            by_face=by_face,
            net_name=net_name,
            data_aux=data_aux,
        )
