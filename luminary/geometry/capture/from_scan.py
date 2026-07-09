"""Camera lighting-scan capture: interface-only stub (spec §7.4, review §19.9).

Defines the stable data contract now so the CV implementation can slot in
later as a drop-in alternative to :mod:`from_scaffold` — never a parallel
pipeline. Calling :func:`capture` raises ``NotImplementedError``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from luminary.geometry.lights import LightsGeometry
from luminary.geometry.scaffold import Scaffold


class CameraSpec(BaseModel):
    """Camera intrinsics and pose for one scan capture session."""

    intrinsics: List[float] = Field(
        description="3x3 row-major camera matrix (fx 0 cx / 0 fy cy / 0 0 1)",
        min_length=9,
        max_length=9,
    )
    pose: List[float] = Field(
        description="4x4 row-major world-from-camera transform",
        min_length=16,
        max_length=16,
    )


class ScanFrame(BaseModel):
    """One captured frame: which light was lit, and where its image lives."""

    controller: int
    channel: int
    index: int
    image: str = Field(description="Path to the captured image file")


class ScanBundle(BaseModel):
    """A complete lighting scan: camera + one frame per individually-lit light."""

    camera: CameraSpec
    frames: List[ScanFrame]
    meta: Dict[str, Any] = Field(default_factory=dict)


def capture(scaffold: Scaffold, bundle: ScanBundle) -> LightsGeometry:
    """Lift per-light image positions onto scaffold lines (not implemented).

    The eventual implementation detects each lit light's centroid in its
    frame, back-projects the camera ray, and intersects it with the nearest
    scaffold line to obtain a scaffold-relative 3D position; output is an
    ordinary :class:`LightsGeometry`.
    """
    raise NotImplementedError(
        "Camera-scan capture is specified but not implemented in 2.1 "
        "(spec §7.4); use capture.from_scaffold instead"
    )
