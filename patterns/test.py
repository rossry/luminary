"""Test pattern for infrastructure validation."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class TestPattern(LuminaryPattern):
    """Simple test pattern that demonstrates the basic infrastructure."""
    
    @property
    def name(self) -> str:
        return "Test Pattern"
    
    @property
    def description(self) -> str:
        return "Simple test pattern for infrastructure validation"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate simple pattern with rotating hue offset."""
        n_beams = beam_array.shape[0]
        
        # Create OKLCH output array
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract theta column (polar angle)
        theta = beam_array[:, BeamArrayColumns.THETA]
        
        # Set constant lightness
        oklch_output[:, 0] = 0.6  # Bright but not too bright
        
        # Set constant chroma
        oklch_output[:, 1] = 0.3  # Moderate chroma
        
        # Vary hue based on theta with rotating time offset
        # Convert theta from radians to degrees and add time-based rotation
        hue_offset = (t * 60.0) % 360.0  # Rotate 60 degrees per second
        hue = (theta * 180.0 / np.pi + hue_offset) % 360.0
        oklch_output[:, 2] = hue
        
        return oklch_output