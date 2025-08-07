"""Spiral pattern with rotating arms and color gradient."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class SpiralPattern(LuminaryPattern):
    """Rotating spiral arms with radial color gradient."""
    
    @property
    def name(self) -> str:
        return "Spiral Pattern"
    
    @property
    def description(self) -> str:
        return "Rotating spiral arms with radial gradient"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate spiral pattern with rotating arms.
        
        Creates logarithmic spiral arms that rotate around the center,
        with lightness varying based on proximity to spiral arms
        and hue shifting along the spiral.
        """
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract polar coordinates
        r = beam_array[:, BeamArrayColumns.R]      # Distance from center
        theta = beam_array[:, BeamArrayColumns.THETA]  # Angle
        
        # Spiral parameters
        num_arms = 3           # Number of spiral arms
        spiral_tightness = 0.3  # How tightly wound the spiral is
        rotation_speed = 45.0   # Degrees per second
        
        # Calculate spiral arm positions
        spiral_intensity = np.zeros_like(r)
        
        for arm_idx in range(num_arms):
            # Base angle for this arm
            arm_base_angle = arm_idx * (2 * np.pi / num_arms)
            
            # Add rotation over time
            arm_angle = arm_base_angle + np.radians(t * rotation_speed)
            
            # Logarithmic spiral equation: theta = theta_0 + b * ln(r)
            # For each radius, calculate where the spiral arm should be
            spiral_angle = arm_angle + spiral_tightness * np.log(np.maximum(r, 0.1))
            
            # Find angular distance to spiral arm
            angle_diff = np.abs(((theta - spiral_angle + np.pi) % (2 * np.pi)) - np.pi)
            
            # Convert to intensity (closer to arm = brighter)
            arm_width = 0.4  # Radians
            arm_intensity = np.exp(-angle_diff / arm_width)
            
            # Fade intensity with distance from center
            radial_falloff = np.exp(-r / 30.0)
            arm_intensity *= radial_falloff
            
            spiral_intensity += arm_intensity
        
        # Clamp intensity
        spiral_intensity = np.clip(spiral_intensity, 0, 1)
        
        # Base lighting with spiral enhancement
        base_lightness = 0.15
        oklch_output[:, 0] = base_lightness + spiral_intensity * 0.7
        
        # Chroma varies with spiral intensity and radius
        base_chroma = 0.1
        oklch_output[:, 1] = base_chroma + spiral_intensity * 0.3
        
        # Hue based on angle and radius with time rotation
        # Create color flow along the spiral
        hue_base = np.degrees(theta) + r * 3.0 + t * 20.0  # Slow hue rotation
        hue_spiral_shift = spiral_intensity * 60.0  # Shift hue on spiral arms
        oklch_output[:, 2] = (hue_base + hue_spiral_shift) % 360.0
        
        return oklch_output