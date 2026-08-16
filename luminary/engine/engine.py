"""The core engine: lights + pattern + t -> wire frames (spec §10).

This is the single place the pipeline is assembled (spec §10.2.2): both the
serial and WebSocket drivers call exactly ``frame(t)`` and transport the
returned bytes. The engine imports no web or serial code (spec §2.2.2).
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

import numpy as np

from luminary.color import convert
from luminary.comms.codec import CodecConfig, Encoder, EncoderStats
from luminary.geometry.lights import LightsGeometry
from luminary.patterns.base import Pattern


class Engine:
    """Holds a lights geometry, the current pattern, and the codec session."""

    def __init__(
        self,
        lights: LightsGeometry,
        pattern: Pattern,
        *,
        fps: float = 30.0,
        codec_config: Optional[CodecConfig] = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.lights = lights
        self.pattern = pattern
        self.fps = fps
        self.codec_config = codec_config or CodecConfig()
        self.encoder = Encoder(lights, self.codec_config)

    # ------------------------------------------------------------------ control

    def set_pattern(self, pattern: Pattern) -> None:
        """Hot-swap the pattern; takes effect next frame with a keyframe (§10.4)."""
        self.pattern = pattern
        self.encoder.force_keyframe()

    def set_lights(self, lights: LightsGeometry) -> None:
        """Swap geometry; resets the codec session entirely (spec §10.2.1)."""
        self.lights = lights
        self.encoder = Encoder(lights, self.codec_config)

    def request_keyframe(self) -> None:
        """Decoder resync request or new consumer joined (spec §11.7.3)."""
        self.encoder.force_keyframe()

    # ------------------------------------------------------------------- frames

    def session_frames(self, t: float = 0.0) -> List[bytes]:
        return self.encoder.session_frames(t)

    def frame(self, t: float) -> List[bytes]:
        """Render + encode one frame: the whole per-frame pipeline (§10.2.2)."""
        oklch = self.pattern.render(self.lights.array, float(t))
        return self.encoder.encode(oklch, float(t))

    def frames(self, start_frame: int = 0) -> Iterator[Tuple[float, List[bytes]]]:
        """Unpaced generator of (t, wire frames); pacing belongs to drivers."""
        i = start_frame
        while True:
            t = i / self.fps
            yield t, self.frame(t)
            i += 1

    # -------------------------------------------------------- authoring outputs

    def colors_oklch(self, t: float) -> np.ndarray:
        """(n,3) OKLCH for all rows — the pattern's ground truth (spec §10.5)."""
        return self.pattern.render(self.lights.array, float(t))

    def colors_srgb8(self, t: float) -> np.ndarray:
        """(n,3) uint8 sRGB for all rows, for static rendering (spec §10.5.1)."""
        return convert.oklch_to_srgb8(self.colors_oklch(t))

    @property
    def stats(self) -> EncoderStats:
        return self.encoder.stats
