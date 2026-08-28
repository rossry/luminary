"""The Pattern contract (spec §9.1).

A pattern is a pure, vectorized function of the lights array and a time in
seconds. It must be stateless: same (lights, t) in, same OKLCH out, with no
dependence on call order (spec §1.3.4, §9.1.3) — the codec relies on being
able to recompute ground truth at any t.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import numpy as np


class Pattern(ABC):
    """Base class for all patterns.

    Subclasses set ``name`` (a stable slug used by the CLI/API) and
    ``description``, and implement :meth:`render`.
    """

    name: str = "unnamed"
    description: str = ""
    #: Liner notes: a few evocative sentences for whoever is running the
    #: show — what the scene is and where it is going. Shown in italics
    #: on viewer surfaces; empty is fine.
    notes: str = ""

    @abstractmethod
    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        """Compute OKLCH for every light at time t.

        Args:
            lights: (n, N_LIGHT_COLUMNS) lights array (spec §6.3); index
                columns via :class:`luminary.geometry.lights.LightColumns`.
            t: elapsed seconds (float).

        Returns:
            (n, 3) float array [L, C, H]: L in [0,1], C in [0, ~0.4],
            H in degrees. Must be finite for rows with finite coordinates,
            computed with vectorized NumPy only.
        """

    def info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "notes": self.notes,
            "class_name": type(self).__name__,
        }
