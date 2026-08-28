"""Mapped production capture: the net design plus the recorded wiring.

`capture()` describes the *design* — one light per beam, with no idea which
board or strip drives it, so everything lands on controller 0. This module
closes that gap (spec §7.3.1, §19.6): it takes the per-board mapping records
an operator confirmed with ``luminary map`` and produces the geometry the
installation actually has, with real ``(controller, channel, index)``
identities.

Each strip LED inherits the *beam* it illuminates. That is the physical
truth: the design's unit is a beam, and at a panel's native density the strip
maps onto beams one-for-one, while a 360-LED strip on a 180-beam panel has
two LEDs lighting each beam. Inheriting position and display shape from the
referenced beam therefore gives coincident LEDs the same colour, which is
what actually happens on the cloth.

The strip path and the index-to-beam bridge come from
``luminary.mapping.strip_path``, shared with the mapping session — so a
deployment renders the way the tool that mapped it said it would.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from luminary.geometry.lights import LightColumns, LightsGeometry, LightSpec
from luminary.geometry.net import Net
from luminary.geometry.pentagon.adapters import capture
from luminary.mapping.plan import Plan
from luminary.mapping.state import BoardRecord
from luminary.mapping.strip_path import StripPaths

_CONFIGS = Path(__file__).resolve().parents[3] / "configs"


class MappingIncompleteError(ValueError):
    """The records do not describe a drivable installation."""


def capture_mapped(
    net: Net,
    plan: Plan,
    boards: Dict[int, BoardRecord],
    *,
    net_lights: Optional[LightsGeometry] = None,
    strict: bool = True,
) -> LightsGeometry:
    """Net + mapping records -> the deployed geometry.

    ``strict`` refuses a partial mapping. Turn it off to drive whatever has
    been mapped so far — useful mid-commissioning, and honest about what it
    is: the unmapped panels are simply absent, so they stay dark.
    """
    net_lights = net_lights if net_lights is not None else capture(net)
    geometry = json.loads((_CONFIGS / f"{plan.net_name}.json").read_text())["geometry"]
    xy = net_lights.array[:, [LightColumns.X, LightColumns.Y]]
    strips = StripPaths(geometry, xy)

    # Reuse the serialized form: it already carries each beam's display
    # polygon, throw direction, extent, and folded 3-D position, so a strip
    # LED inherits the full description of the beam it lights.
    source_rows = net_lights.to_file_dict()["lights"]

    mapped: List[LightSpec] = []
    seen: Dict[int, int] = {}
    for unit in plan.units:
        record = boards.get(unit)
        if record is None or record.controller_id is None:
            if strict:
                raise MappingIncompleteError(
                    f"unit {unit} has no controller locked; run `luminary map`"
                )
            continue
        controller = record.controller_id
        if controller in seen and seen[controller] != unit:
            raise MappingIncompleteError(
                f"controller {controller} is claimed by units "
                f"{seen[controller]} and {unit}"
            )
        seen[controller] = unit

        expected = len(plan.panels[unit])
        if strict and len(record.channels) != expected:
            raise MappingIncompleteError(
                f"unit {unit} (controller {controller}) has "
                f"{len(record.channels)}/{expected} panels mapped"
            )

        for channel, channel_record in sorted(record.channels.items()):
            panel = plan.by_face[channel_record.face]
            refs = strips.strip_refs(
                panel, channel_record.density, channel_record.winding
            )
            for index, ref in enumerate(refs):
                entry = dict(source_rows[int(ref)])
                entry["controller"] = controller
                entry["channel"] = channel
                entry["index"] = index
                mapped.append(LightSpec.model_validate(entry))

    if not mapped:
        raise MappingIncompleteError(
            "no panels are mapped; run `luminary map` before building geometry"
        )

    meta = dict(net_lights.meta)
    meta["name"] = f"{plan.net_name}-mapped"
    meta["mapped"] = {
        "controllers": sorted(seen),
        "panels": sum(len(b.channels) for b in boards.values() if b is not None),
        "lights": len(mapped),
    }
    source = dict(net_lights.source)
    source["type"] = "pentagon-mapped"
    source["net"] = plan.net_name
    return LightsGeometry.from_specs(
        mapped, space=net_lights.space, source=source, meta=meta
    )
