"""Breathing pattern with gentle pulsing luminance."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class BreathePattern(LuminaryPattern):
    """Gentle breathing pattern with pulsing luminance."""
    
    @property
    def name(self) -> str:
        return "Breathe Pattern"
    
    @property
    def description(self) -> str:
        return "Gentle breathing with pulsing luminance"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate breathing pattern with smooth pulsing.
        
        Creates a gentle breathing effect with sinusoidal luminance
        variation, subtle chroma modulation, and slow hue shifts
        that create a calming, organic feeling.
        """
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract spatial coordinates for subtle variation
        r = beam_array[:, BeamArrayColumns.R]      # Distance from center
        theta = beam_array[:, BeamArrayColumns.THETA]  # Angle
        
        # Breathing parameters
        breath_rate = 0.3      # Breaths per second (very slow)
        breath_depth = 0.6     # How much lightness varies
        pulse_rate = 0.15      # Even slower pulse for chroma
        hue_drift_rate = 8.0   # Very slow hue changes (degrees per second)
        
        # Primary breathing wave (lightness)
        breath_phase = t * breath_rate * 2 * np.pi
        breath_wave = np.sin(breath_phase)
        
        # Convert to 0-1 range and apply easing for more organic feel
        breath_intensity = (breath_wave + 1.0) / 2.0
        # Apply ease-in-out for more natural breathing rhythm
        breath_intensity = 3 * breath_intensity**2 - 2 * breath_intensity**3
        
        # Secondary pulse for chroma variation
        pulse_phase = t * pulse_rate * 2 * np.pi + np.pi/4  # Phase offset
        pulse_wave = np.sin(pulse_phase)
        pulse_intensity = (pulse_wave + 1.0) / 2.0
        
        # Subtle spatial variation - closer to center breathes more
        radial_factor = 1.0 - np.exp(-r / 25.0)  # Inverse exponential
        spatial_breath = 1.0 - radial_factor * 0.3
        
        # Angular variation - very subtle
        angular_variation = np.sin(theta * 2) * 0.05 + 1.0  # Very small variation
        
        # Calculate lightness with breathing
        base_lightness = 0.25
        breath_modulation = breath_intensity * breath_depth * spatial_breath * angular_variation
        oklch_output[:, 0] = base_lightness + breath_modulation
        
        # Chroma varies with pulse and breathing
        base_chroma = 0.15
        chroma_breath = breath_intensity * 0.1
        chroma_pulse = pulse_intensity * 0.15
        oklch_output[:, 1] = base_chroma + chroma_breath + chroma_pulse
        
        # Very slow hue drift with subtle spatial and temporal variation
        base_hue = (t * hue_drift_rate) % 360.0
        
        # Add very subtle spatial hue variation
        spatial_hue = np.degrees(theta) * 0.1  # Very small angular shift
        radial_hue = r * 0.5  # Subtle radial shift
        
        # Breathing affects hue slightly
        hue_breath = breath_intensity * 15.0 - 7.5  # ±7.5 degree shift
        
        oklch_output[:, 2] = (base_hue + spatial_hue + radial_hue + hue_breath) % 360.0
        
        return oklch_output