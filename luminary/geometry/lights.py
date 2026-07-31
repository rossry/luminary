"""Lights geometry: the canonical per-light representation (spec §6).

One row per light in a single NumPy array (`LightsGeometry.array`), columns
defined once by :class:`LightColumns`. Everything downstream — patterns, the
codec, renderers — is defined in terms of this array; there is no other
per-light representation (spec §1.3.1, §6.1.1).

Rows are sorted by (controller, channel, index) — the same order the codec
walks and the firmware addresses (spec §6.4).
"""

from __future__ import annotations

import json
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
from pydantic import BaseModel, Field, field_validator

from luminary.geometry import coords

LIGHTS_SCHEMA = "luminary.lights/1"
MAX_CHANNELS = 8


class Kind(IntEnum):
    """Control kind of a light (spec §6.2.2)."""

    ACTIVE = 0
    INTERPOLATED = 1
    INACTIVE = 2


_KIND_NAMES = {
    "active": Kind.ACTIVE,
    "interpolated": Kind.INTERPOLATED,
    "inactive": Kind.INACTIVE,
}
_KIND_STRINGS = {v: k for k, v in _KIND_NAMES.items()}


class LightColumns(IntEnum):
    """Column indices of the lights array (spec §6.3.1). Append-only."""

    CONTROLLER = 0
    CHANNEL = 1
    INDEX = 2
    KIND = 3
    WEIGHT = 4
    X = 5
    Y = 6
    R = 7
    THETA = 8
    X3 = 9
    Y3 = 10
    Z3 = 11
    RHO = 12
    THETA_S = 13
    PHI_S = 14
    DX = 15
    DY = 16
    DZ = 17
    EX = 18
    EY = 19
    EZ = 20
    NX = 21
    NY = 22
    NZ = 23


N_LIGHT_COLUMNS = len(LightColumns)


class SpaceSpec(BaseModel):
    """Which coordinate space(s) a geometry file specifies directly (spec §4.1.2)."""

    authoritative: List[str] = Field(default=["xy"], min_length=1)
    projection: Optional[str] = None
    angle_units: str = "deg"

    @field_validator("authoritative")
    @classmethod
    def _check_spaces(cls, v: List[str]) -> List[str]:
        for space in v:
            if space not in ("xy", "xyz"):
                raise ValueError(f"Unknown authoritative space: {space!r}")
        return v

    @field_validator("angle_units")
    @classmethod
    def _check_units(cls, v: str) -> str:
        if v not in ("deg", "rad"):
            raise ValueError(f"angle_units must be 'deg' or 'rad', got {v!r}")
        return v

    def requires_projection(self) -> bool:
        return "xyz" in self.authoritative and "xy" not in self.authoritative


class LightSpec(BaseModel):
    """One light in a *.lights.json file (spec §6.5.1)."""

    controller: int = Field(ge=0)
    channel: int = Field(ge=0, lt=MAX_CHANNELS)
    index: int = Field(ge=0)
    kind: str = "active"
    pos: Optional[List[float]] = None
    dir: Optional[List[float]] = None
    extent: Optional[List[float]] = None
    normal: Optional[List[float]] = None
    display: Optional[List[List[float]]] = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in _KIND_NAMES:
            raise ValueError(f"kind must be one of {sorted(_KIND_NAMES)}, got {v!r}")
        return v

    @field_validator("pos")
    @classmethod
    def _check_pos(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) not in (2, 3):
            raise ValueError("pos must have 2 or 3 components")
        return v

    @field_validator("dir", "extent", "normal")
    @classmethod
    def _check_vec3(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 3:
            raise ValueError("dir/extent/normal must have 3 components")
        return v


class LightsFile(BaseModel):
    """Root schema of a *.lights.json document (spec §6.5.1)."""

    schema_id: str = Field(default=LIGHTS_SCHEMA, alias="schema")
    space: SpaceSpec = Field(default_factory=SpaceSpec)
    source: Dict[str, Any] = Field(default_factory=dict)
    lights: List[LightSpec]
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("schema_id")
    @classmethod
    def _check_schema(cls, v: str) -> str:
        if v != LIGHTS_SCHEMA:
            raise ValueError(f"Unsupported lights schema: {v!r}")
        return v


class LightsGeometryError(ValueError):
    """Raised for invalid lights geometry (spec §6.6.3)."""


class LightsGeometry:
    """The canonical lights table: numeric array + display shapes + provenance."""

    def __init__(
        self,
        array: np.ndarray,
        display: List[Optional[List[List[float]]]],
        space: SpaceSpec,
        source: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> None:
        if array.ndim != 2 or array.shape[1] != N_LIGHT_COLUMNS:
            raise LightsGeometryError(
                f"lights array must be (n, {N_LIGHT_COLUMNS}), got {array.shape}"
            )
        self.array = array
        self.display = display
        self.space = space
        self.source = source
        self.meta = meta

    # ---------------------------------------------------------------- accessors

    @property
    def n(self) -> int:
        return int(self.array.shape[0])

    @property
    def control_mask(self) -> np.ndarray:
        """(n,) bool selecting ACTIVE rows (spec §6.6.2)."""
        mask: np.ndarray = self.array[:, LightColumns.KIND] == Kind.ACTIVE
        return mask

    def ints(self, column: LightColumns) -> np.ndarray:
        """Integer-semantics column as an int array (spec §6.3.2)."""
        return self.array[:, column].astype(np.int64)

    @property
    def controllers(self) -> List[int]:
        return sorted(int(c) for c in np.unique(self.ints(LightColumns.CONTROLLER)))

    def rows_for_controller(self, controller: int) -> np.ndarray:
        """Row indices belonging to a controller, in canonical order."""
        return np.flatnonzero(self.ints(LightColumns.CONTROLLER) == controller)

    def active_rows_for_controller(self, controller: int) -> np.ndarray:
        """ACTIVE row indices for a controller, in canonical (wire) order."""
        mask = (self.ints(LightColumns.CONTROLLER) == controller) & self.control_mask
        return np.flatnonzero(mask)

    def channel_strips(self, controller: int) -> Dict[int, Dict[str, Any]]:
        """Per-channel strip layout for SESSION frames (spec §11.7.2).

        Returns {channel: {"length": int, "kinds": (len,) uint8,
        "weights": (len,) uint8}} where positions not present in the geometry
        are INACTIVE. Weights are quantized to u8 (0..255).
        """
        out: Dict[int, Dict[str, Any]] = {}
        rows = self.rows_for_controller(controller)
        channels = self.ints(LightColumns.CHANNEL)[rows]
        indices = self.ints(LightColumns.INDEX)[rows]
        kinds = self.ints(LightColumns.KIND)[rows]
        weights = self.array[rows, LightColumns.WEIGHT]
        for channel in sorted(set(int(c) for c in channels)):
            sel = channels == channel
            ch_idx = indices[sel]
            length = int(ch_idx.max()) + 1
            kind_arr = np.full(length, int(Kind.INACTIVE), dtype=np.uint8)
            weight_arr = np.zeros(length, dtype=np.uint8)
            kind_arr[ch_idx] = kinds[sel]
            w = weights[sel]
            w8 = np.clip(np.rint(np.nan_to_num(w, nan=0.0) * 255.0), 0, 255)
            weight_arr[ch_idx] = w8.astype(np.uint8)
            out[channel] = {
                "length": length,
                "kinds": kind_arr,
                "weights": weight_arr,
            }
        return out

    # ---------------------------------------------------------------- build/load

    @classmethod
    def from_specs(
        cls,
        lights: Sequence[LightSpec],
        space: SpaceSpec,
        source: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "LightsGeometry":
        if not lights:
            raise LightsGeometryError("lights geometry contains no lights")

        n = len(lights)
        identity = np.array(
            [(s.controller, s.channel, s.index) for s in lights], dtype=np.int64
        )
        order = np.lexsort((identity[:, 2], identity[:, 1], identity[:, 0]))
        specs = [lights[i] for i in order]
        identity = identity[order]

        dupes = np.flatnonzero(
            np.all(np.diff(identity, axis=0) == 0, axis=1) if n > 1 else np.array([])
        )
        if dupes.size:
            c, ch, i = identity[dupes[0] + 1]
            raise LightsGeometryError(
                f"Duplicate light identity controller={c} channel={ch} index={i}"
            )

        array = np.full((n, N_LIGHT_COLUMNS), np.nan, dtype=np.float64)
        array[:, LightColumns.CONTROLLER] = identity[:, 0]
        array[:, LightColumns.CHANNEL] = identity[:, 1]
        array[:, LightColumns.INDEX] = identity[:, 2]
        array[:, LightColumns.KIND] = [_KIND_NAMES[s.kind] for s in specs]

        # Authoritative positions (rows without pos stay NaN until interpolated).
        use_xyz = "xyz" in space.authoritative
        pos_dim = 3 if use_xyz else 2
        pos = np.full((n, pos_dim), np.nan)
        for row, spec in enumerate(specs):
            if spec.pos is not None:
                p = spec.pos
                if use_xyz:
                    pos[row] = p if len(p) == 3 else [p[0], p[1], 0.0]
                else:
                    pos[row] = p[:2]

        # Fill missing INTERPOLATED positions by index-fraction lerp between
        # bounding lights that have positions, per channel (spec §6.5.1).
        _fill_missing_positions(identity, pos, specs)

        if use_xyz:
            block = coords.derive_all(None, pos, space.projection)
        else:
            block = coords.derive_all(pos, None, None)
        array[:, LightColumns.X : LightColumns.PHI_S + 1] = block

        for row, spec in enumerate(specs):
            if spec.dir is not None:
                d = np.asarray(spec.dir, dtype=np.float64)
                norm = float(np.linalg.norm(d))
                if norm > 0:
                    d = d / norm
                array[row, LightColumns.DX : LightColumns.DZ + 1] = d
            if spec.extent is not None:
                array[row, LightColumns.EX : LightColumns.EZ + 1] = spec.extent
            if spec.normal is not None:
                array[row, LightColumns.NX : LightColumns.NZ + 1] = spec.normal

        display: List[Optional[List[List[float]]]] = [s.display for s in specs]

        geometry = cls(
            array=array,
            display=display,
            space=space,
            source=dict(source or {}),
            meta=dict(meta or {}),
        )
        geometry._compute_weights()
        return geometry

    @classmethod
    def load(cls, source: Union[str, Path, Dict[str, Any]]) -> "LightsGeometry":
        """Load and validate from a path or an already-parsed dict (spec §6.6.1)."""
        if isinstance(source, (str, Path)):
            doc = json.loads(Path(source).read_text())
        else:
            doc = source
        parsed = LightsFile.model_validate(doc)
        if parsed.space.requires_projection() and parsed.space.projection is None:
            raise LightsGeometryError(
                "space.projection is required when xyz is the authoritative space"
            )
        return cls.from_specs(parsed.lights, parsed.space, parsed.source, parsed.meta)

    def to_file_dict(self) -> Dict[str, Any]:
        """Serialize authoritative quantities only (spec §6.5.2)."""
        use_xyz = "xyz" in self.space.authoritative
        lights: List[Dict[str, Any]] = []
        arr = self.array
        for row in range(self.n):
            entry: Dict[str, Any] = {
                "controller": int(arr[row, LightColumns.CONTROLLER]),
                "channel": int(arr[row, LightColumns.CHANNEL]),
                "index": int(arr[row, LightColumns.INDEX]),
                "kind": _KIND_STRINGS[Kind(int(arr[row, LightColumns.KIND]))],
            }
            if use_xyz:
                p = arr[row, LightColumns.X3 : LightColumns.Z3 + 1]
            else:
                p = arr[row, LightColumns.X : LightColumns.Y + 1]
            if not np.any(np.isnan(p)):
                entry["pos"] = [float(v) for v in p]
            d = arr[row, LightColumns.DX : LightColumns.DZ + 1]
            if not np.any(np.isnan(d)):
                entry["dir"] = [float(v) for v in d]
            e = arr[row, LightColumns.EX : LightColumns.EZ + 1]
            if not np.any(np.isnan(e)):
                entry["extent"] = [float(v) for v in e]
            nrm = arr[row, LightColumns.NX : LightColumns.NZ + 1]
            if not np.any(np.isnan(nrm)):
                entry["normal"] = [float(v) for v in nrm]
            if self.display[row] is not None:
                entry["display"] = self.display[row]
            lights.append(entry)
        return {
            "schema": LIGHTS_SCHEMA,
            "space": self.space.model_dump(exclude_none=True),
            "source": self.source,
            "lights": lights,
            "meta": self.meta,
        }

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_file_dict(), indent=2))

    # ---------------------------------------------------------------- internals

    def _compute_weights(self) -> None:
        """Interpolation weights from along-strip distance (spec §6.2.3)."""
        arr = self.array
        kinds = self.ints(LightColumns.KIND)
        controllers = self.ints(LightColumns.CONTROLLER)
        channels = self.ints(LightColumns.CHANNEL)
        arr[:, LightColumns.WEIGHT] = np.nan

        for controller in self.controllers:
            for channel in np.unique(channels[controllers == controller]):
                rows = np.flatnonzero(
                    (controllers == controller) & (channels == channel)
                )
                strip_kinds = kinds[rows]
                interp_local = np.flatnonzero(strip_kinds == Kind.INTERPOLATED)
                if interp_local.size == 0:
                    continue
                active_local = np.flatnonzero(strip_kinds == Kind.ACTIVE)
                if active_local.size == 0:
                    raise LightsGeometryError(
                        f"controller {controller} channel {channel} has interpolated "
                        "lights but no active lights"
                    )
                cols = np.array(
                    [LightColumns.X3, LightColumns.Y3, LightColumns.Z3],
                    dtype=np.intp,
                )
                pos = arr[np.ix_(rows, cols)]
                seg = np.linalg.norm(np.diff(pos, axis=0), axis=1)
                s = np.concatenate([[0.0], np.cumsum(seg)])

                prev_idx = np.searchsorted(active_local, interp_local, side="left") - 1
                next_idx = np.searchsorted(active_local, interp_local, side="left")
                bad = (prev_idx < 0) | (next_idx >= active_local.size)
                if np.any(bad):
                    row = rows[interp_local[np.flatnonzero(bad)[0]]]
                    raise LightsGeometryError(
                        "Interpolated light without bounding active lights: "
                        f"controller {controller} channel {channel} "
                        f"index {int(arr[row, LightColumns.INDEX])}"
                    )
                s_prev = s[active_local[prev_idx]]
                s_next = s[active_local[next_idx]]
                span = s_next - s_prev
                w = np.where(
                    span > 0,
                    (s[interp_local] - s_prev) / np.where(span > 0, span, 1.0),
                    0.5,
                )
                arr[rows[interp_local], LightColumns.WEIGHT] = w


def _fill_missing_positions(
    identity: np.ndarray, pos: np.ndarray, specs: Sequence[LightSpec]
) -> None:
    """Lerp missing positions between bounding positioned lights on a channel."""
    n = identity.shape[0]
    missing = np.flatnonzero(np.any(np.isnan(pos), axis=1))
    if missing.size == 0:
        return
    for row in (int(r) for r in missing):
        if specs[row].kind != "interpolated":
            raise LightsGeometryError(
                f"Light controller={identity[row,0]} channel={identity[row,1]} "
                f"index={identity[row,2]} has no pos and is not interpolated"
            )
        controller, channel, index = identity[row]
        strip = np.flatnonzero(
            (identity[:, 0] == controller) & (identity[:, 1] == channel)
        )
        has_pos = strip[~np.any(np.isnan(pos[strip]), axis=1)]
        before = has_pos[identity[has_pos, 2] < index]
        after = has_pos[identity[has_pos, 2] > index]
        if before.size == 0 or after.size == 0:
            raise LightsGeometryError(
                "Interpolated light without positioned neighbors: "
                f"controller {controller} channel {channel} index {index}"
            )
        p_row, n_row = before[-1], after[0]
        i0, i1 = identity[p_row, 2], identity[n_row, 2]
        frac = (index - i0) / (i1 - i0)
        pos[row] = pos[p_row] + frac * (pos[n_row] - pos[p_row])
    if n and np.any(np.isnan(pos)):
        raise LightsGeometryError("Unresolvable missing positions in lights geometry")
