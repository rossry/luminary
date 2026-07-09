"""Scaffold geometry: structural lines of the installation (spec §5).

A scaffold line has endpoints p1/p2, an optional explicit midpoint (for lines
that bend across a non-planar manifold), and three normals sampled at p1, the
midpoint, and p2. A normal is the in-surface lateral direction pointing away
from the line to one side (spec §4.4.1) — the direction mounted lights throw.

This is a load/author-time object; no per-frame code touches it (spec §5.4.2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
from pydantic import BaseModel, Field, field_validator

from luminary.geometry import coords
from luminary.geometry.lights import SpaceSpec

SCAFFOLD_SCHEMA = "luminary.scaffold/1"


class LineSpec(BaseModel):
    """One scaffold line in a *.scaffold.json file (spec §5.3.1)."""

    id: Optional[str] = None
    p1: List[float]
    p2: List[float]
    midpoint: Optional[List[float]] = None
    n1: Optional[List[float]] = None
    n_mid: Optional[List[float]] = None
    n2: Optional[List[float]] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("p1", "p2", "midpoint")
    @classmethod
    def _check_point(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) not in (2, 3):
            raise ValueError("points must have 2 or 3 components")
        return v

    @field_validator("n1", "n_mid", "n2")
    @classmethod
    def _check_normal(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 3:
            raise ValueError("normals must have 3 components")
        return v


class ScaffoldFile(BaseModel):
    """Root schema of a *.scaffold.json document (spec §5.3.1)."""

    schema_id: str = Field(default=SCAFFOLD_SCHEMA, alias="schema")
    space: SpaceSpec = Field(default_factory=SpaceSpec)
    lines: List[LineSpec]
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("schema_id")
    @classmethod
    def _check_schema(cls, v: str) -> str:
        if v != SCAFFOLD_SCHEMA:
            raise ValueError(f"Unsupported scaffold schema: {v!r}")
        return v


class ScaffoldError(ValueError):
    """Raised for invalid scaffold geometry."""


class Scaffold:
    """A validated scaffold with fully-derived coordinates (spec §5.4).

    Vectorized accessors:
      - ``p1_xyz``, ``mid_xyz``, ``p2_xyz``: (n,3) spatial points
      - ``p1_xy``, ``mid_xy``, ``p2_xy``: (n,2) drawing-plane points
      - ``normals``: (n,3,3) — [n1, n_mid, n2] per line, unit vectors
    """

    def __init__(
        self,
        lines: List[LineSpec],
        space: SpaceSpec,
        meta: Dict[str, Any],
    ) -> None:
        if not lines:
            raise ScaffoldError("scaffold contains no lines")
        if space.requires_projection() and space.projection is None:
            raise ScaffoldError(
                "space.projection is required when xyz is the authoritative space"
            )
        self.lines = lines
        self.space = space
        self.meta = meta

        n = len(lines)
        use_xyz = "xyz" in space.authoritative

        def to3(p: List[float]) -> List[float]:
            return list(p) if len(p) == 3 else [p[0], p[1], 0.0]

        p1 = np.array([to3(line.p1) for line in lines], dtype=np.float64)
        p2 = np.array([to3(line.p2) for line in lines], dtype=np.float64)
        mid = np.array(
            [
                to3(line.midpoint) if line.midpoint is not None else [0.0, 0.0, 0.0]
                for line in lines
            ],
            dtype=np.float64,
        )
        no_mid = np.array([line.midpoint is None for line in lines])
        mid[no_mid] = 0.5 * (p1[no_mid] + p2[no_mid])

        self.p1_xyz = p1
        self.p2_xyz = p2
        self.mid_xyz = mid

        if use_xyz:
            projection = space.projection or "orthographic_xy"
            self.p1_xy = coords.project(p1, projection)
            self.p2_xy = coords.project(p2, projection)
            self.mid_xy = coords.project(mid, projection)
        else:
            self.p1_xy = p1[:, 0:2].copy()
            self.p2_xy = p2[:, 0:2].copy()
            self.mid_xy = mid[:, 0:2].copy()

        # Normals: default is the in-plane lateral direction +90deg CCW of the
        # p1->p2 direction (spec §5.3.2), the same for all three samples.
        chord = p2 - p1
        chord_norm = np.linalg.norm(chord[:, 0:2], axis=1)
        if np.any(chord_norm == 0):
            bad = int(np.flatnonzero(chord_norm == 0)[0])
            raise ScaffoldError(f"scaffold line {bad} has coincident endpoints")
        default_normal = np.stack(
            [-chord[:, 1] / chord_norm, chord[:, 0] / chord_norm, np.zeros(n)],
            axis=1,
        )
        normals = np.empty((n, 3, 3), dtype=np.float64)
        for sample, attr in enumerate(("n1", "n_mid", "n2")):
            explicit = np.array(
                [
                    (
                        getattr(line, attr)
                        if getattr(line, attr) is not None
                        else [0, 0, 0]
                    )
                    for line in lines
                ],
                dtype=np.float64,
            )
            has = np.array([getattr(line, attr) is not None for line in lines])
            vec = np.where(has[:, None], explicit, default_normal)
            length = np.linalg.norm(vec, axis=1, keepdims=True)
            if np.any(length == 0):
                bad = int(np.flatnonzero(length[:, 0] == 0)[0])
                raise ScaffoldError(f"scaffold line {bad} has zero-length {attr}")
            normals[:, sample, :] = vec / length
        self.normals = normals

    @property
    def n_lines(self) -> int:
        return len(self.lines)

    def bounds_xy(self) -> np.ndarray:
        """(2,2) [[min_x, min_y], [max_x, max_y]] over endpoints and midpoints."""
        pts = np.concatenate([self.p1_xy, self.mid_xy, self.p2_xy], axis=0)
        return np.stack([pts.min(axis=0), pts.max(axis=0)])

    @classmethod
    def load(cls, source: Union[str, Path, Dict[str, Any]]) -> "Scaffold":
        if isinstance(source, (str, Path)):
            doc = json.loads(Path(source).read_text())
        else:
            doc = source
        parsed = ScaffoldFile.model_validate(doc)
        return cls(parsed.lines, parsed.space, parsed.meta)

    def to_file_dict(self) -> Dict[str, Any]:
        return {
            "schema": SCAFFOLD_SCHEMA,
            "space": self.space.model_dump(exclude_none=True),
            "lines": [line.model_dump(exclude_none=True) for line in self.lines],
            "meta": self.meta,
        }

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_file_dict(), indent=2))
