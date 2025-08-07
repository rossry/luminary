"""Ripple pattern with expanding circular waves."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class RipplePattern(LuminaryPattern):
    """Expanding circular waves pattern from net center."""
    
    @property
    def name(self) -> str:
        return "Ripple Pattern"
    
    @property
    def description(self) -> str:
        return "Expanding circular waves with rotating hue"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate ripple pattern with expanding waves.
        
        Creates circular waves that expand outward from the center,
        with lightness varying based on distance from expanding ring
        and hue rotating over time.
        """
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract spatial coordinates
        r = beam_array[:, BeamArrayColumns.R]  # Distance from center
        
        # Wave parameters
        wave_speed = 20.0  # Units per second
        wave_length = 15.0  # Distance between wave peaks
        wave_count = 3     # Number of concurrent waves
        
        # Create multiple expanding waves
        wave_intensity = np.zeros_like(r)
        for wave_idx in range(wave_count):
            # Stagger wave start times
            wave_start = wave_idx * (wave_length / wave_speed)
            wave_center = (t - wave_start) * wave_speed
            
            # Only show waves that have started
            if wave_center > 0:
                # Distance from current wave front
                distance_from_wave = np.abs(r - wave_center)
                
                # Intensity falls off with distance from wave front
                intensity = np.exp(-distance_from_wave / (wave_length * 0.3))
                
                # Add wave decay as it gets larger
                decay = np.exp(-wave_center / 50.0)
                intensity *= decay
                
                wave_intensity += intensity
        
        # Clamp intensity
        wave_intensity = np.clip(wave_intensity, 0, 1)
        
        # Lightness varies with wave intensity
        oklch_output[:, 0] = 0.6
        
        # Chroma increases with wave intensity
        oklch_output[:, 1] = 0.15 + wave_intensity * 0.25
        
        # Hue rotates slowly over time with slight spatial variation
        base_hue = (t * 30.0) % 360.0  # 30 degrees per second
        hue_variation = r * 2.0  # Slight radial hue shift
        oklch_output[:, 2] = (base_hue + hue_variation) % 360.0
        
        return oklch_output