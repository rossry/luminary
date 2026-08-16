"""Default capture: lights placed along scaffold lines (spec §7.2).

This is the exit-condition capture method — "produce a lights geometry from a
scaffold + simple defaults". Positions follow each line (a quadratic bend
through the explicit midpoint when one is given); normals interpolate the
line's three sampled normals; direction defaults to the normal (lights throw
across the surface, away from their line, spec §4.4.1).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator

from luminary.geometry.lights import (
    MAX_CHANNELS,
    LightsGeometry,
    LightSpec,
    SpaceSpec,
)
from luminary.geometry.scaffold import Scaffold


class CaptureParams(BaseModel):
    """Parameters for from-scaffold capture (spec §7.2.1).

    Exactly one of ``spacing`` / ``count_per_line`` governs light density
    (default: 10 lights per line). Channel assignment: explicit map by line
    id or tag, else round-robin across lines (spec §7.2.3).
    """

    spacing: Optional[float] = Field(default=None, gt=0)
    count_per_line: Optional[int] = Field(default=None, ge=2)
    controller: int = Field(default=0, ge=0)
    channels: int = Field(default=MAX_CHANNELS, ge=1, le=MAX_CHANNELS)
    start_index: int = Field(default=0, ge=0)
    channel_map: Dict[str, int] = Field(default_factory=dict)
    interpolate_every: Optional[int] = Field(default=None, ge=2)
    throw_distance: Optional[float] = Field(default=None, gt=0)
    extra_lights: List[LightSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_density(self) -> "CaptureParams":
        if self.spacing is not None and self.count_per_line is not None:
            raise ValueError("Give either spacing or count_per_line, not both")
        return self


def _bezier_points(
    p1: np.ndarray, mid: np.ndarray, p2: np.ndarray, u: np.ndarray
) -> np.ndarray:
    """Quadratic Bezier through the midpoint at u=0.5 (spec §7.2.2).

    Control point = 2*mid - (p1+p2)/2 makes the curve pass through ``mid``;
    when ``mid`` is the chord midpoint this reduces exactly to the straight
    line between p1 and p2.
    """
    ctrl = 2.0 * mid - 0.5 * (p1 + p2)
    u = u[:, None]
    out: np.ndarray = (1 - u) ** 2 * p1 + 2 * u * (1 - u) * ctrl + u**2 * p2
    return out


def capture(
    scaffold: Scaffold, params: Optional[CaptureParams] = None
) -> LightsGeometry:
    """Produce a lights geometry from a scaffold with simple defaults."""
    params = params or CaptureParams()
    use_xyz = "xyz" in scaffold.space.authoritative

    next_index: Dict[int, int] = {}
    specs: List[LightSpec] = []

    for line_no in range(scaffold.n_lines):
        line = scaffold.lines[line_no]
        p1 = scaffold.p1_xyz[line_no]
        mid = scaffold.mid_xyz[line_no]
        p2 = scaffold.p2_xyz[line_no]

        channel = _assign_channel(params, line_no, line.id, line.tags)

        if params.spacing is not None:
            length = float(np.linalg.norm(p2 - p1))
            count = max(2, int(np.floor(length / params.spacing)) + 1)
        else:
            count = params.count_per_line or 10

        u = np.linspace(0.0, 1.0, count)
        positions = _bezier_points(p1, mid, p2, u)
        normals = _bezier_points(
            scaffold.normals[line_no, 0],
            scaffold.normals[line_no, 1],
            scaffold.normals[line_no, 2],
            u,
        )
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.where(lengths > 0, lengths, 1.0)

        base = next_index.setdefault(channel, params.start_index)
        for k in range(count):
            pos = positions[k]
            normal = normals[k]
            spec = LightSpec(
                controller=params.controller,
                channel=channel,
                index=base + k,
                kind="active",
                pos=[float(v) for v in (pos if use_xyz else pos[:2])],
                dir=[float(v) for v in normal],
                normal=[float(v) for v in normal],
                extent=(
                    [float(v) for v in (pos + params.throw_distance * normal)]
                    if params.throw_distance is not None
                    else None
                ),
            )
            specs.append(spec)
        next_index[channel] = base + count

    if params.interpolate_every is not None:
        _apply_interpolation_policy(specs, params.interpolate_every)

    specs.extend(params.extra_lights)

    return LightsGeometry.from_specs(
        specs,
        space=SpaceSpec(
            authoritative=list(scaffold.space.authoritative),
            projection=scaffold.space.projection,
        ),
        source={
            "type": "from_scaffold",
            "params": params.model_dump(exclude_none=True, exclude={"extra_lights"}),
        },
        meta={"name": str(scaffold.meta.get("name", "captured")) + "-lights"},
    )


def _assign_channel(
    params: CaptureParams, line_no: int, line_id: Optional[str], tags: List[str]
) -> int:
    if line_id is not None and line_id in params.channel_map:
        return params.channel_map[line_id]
    for tag in tags:
        if tag in params.channel_map:
            return params.channel_map[tag]
    return line_no % params.channels


def _apply_interpolation_policy(specs: List[LightSpec], every: int) -> None:
    """Mark all but 1-in-``every`` lights INTERPOLATED, per channel (spec §7.2.4).

    The first and last light of each channel stay ACTIVE so every
    interpolated light has bounding actives.
    """
    by_channel: Dict[tuple, List[LightSpec]] = {}
    for spec in specs:
        by_channel.setdefault((spec.controller, spec.channel), []).append(spec)
    for channel_specs in by_channel.values():
        channel_specs.sort(key=lambda s: s.index)
        for ordinal, spec in enumerate(channel_specs):
            is_kept = ordinal % every == 0 or ordinal == len(channel_specs) - 1
            spec.kind = "active" if is_kept else "interpolated"
