"""Abstract base class for Luminary patterns."""

from abc import ABC, abstractmethod
import numpy as np


class LuminaryPattern(ABC):
    """Abstract base class for animated geometric patterns using SDFs.
    
    Patterns implement signed distance functions that operate on beam arrays
    to produce OKLCH color values over time. All SDF operations must use
    vectorized numpy operations for performance.
    """

    @abstractmethod
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Evaluate pattern at time t for all beams.
        
        Args:
            beam_array: Array with columns [node, strip, strip_idx, x, y, r, theta, 
                       face, facet, edge, position_index]
            t: Time parameter for animation (typically in seconds)
        
        Returns:
            Array with shape (n_beams, 3) containing OKLCH values [l, c, h] 
            for each beam where:
            - l (lightness): 0.0 (black) to 1.0 (white)
            - c (chroma): 0.0 (gray) to ~0.4 (saturated) 
            - h (hue): 0° to 360° (color wheel position)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable pattern name for display."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Brief pattern description for selection menu."""
        pass
    
    def info(self) -> dict:
        """Get pattern metadata for discovery system.
        
        Returns:
            Dictionary with pattern information including name and description.
        """
        return {
            "name": self.name,
            "description": self.description,
            "class_name": self.__class__.__name__,
        }