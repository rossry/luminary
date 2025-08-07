"""Wave pattern with linear traveling waves."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class WavePattern(LuminaryPattern):
    """Linear traveling waves with configurable direction."""
    
    @property
    def name(self) -> str:
        return "Wave Pattern"
    
    @property
    def description(self) -> str:
        return "Linear traveling waves across the geometry"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate wave pattern with linear traveling waves.
        
        Creates sine waves that travel in a specific direction across
        the geometry, with multiple wave frequencies and directions.
        """
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract cartesian coordinates
        x = beam_array[:, BeamArrayColumns.X]
        y = beam_array[:, BeamArrayColumns.Y]
        
        # Wave parameters
        wave_speed = 25.0      # Units per second
        wave_length_1 = 20.0   # Primary wave
        wave_length_2 = 12.0   # Secondary wave
        wave_length_3 = 35.0   # Long wave
        
        # Multiple wave directions
        # Primary wave: diagonal
        wave_dir_1 = np.array([1, 1]) / np.sqrt(2)  # Normalized diagonal
        # Secondary wave: perpendicular to primary  
        wave_dir_2 = np.array([-1, 1]) / np.sqrt(2) # Perpendicular diagonal
        # Tertiary wave: horizontal
        wave_dir_3 = np.array([1, 0])
        
        # Calculate wave phases for each direction
        # Wave equation: sin(k·r - ωt) where k·r is the dot product
        phase_1 = (x * wave_dir_1[0] + y * wave_dir_1[1]) * (2 * np.pi / wave_length_1) - t * (2 * np.pi * wave_speed / wave_length_1)
        phase_2 = (x * wave_dir_2[0] + y * wave_dir_2[1]) * (2 * np.pi / wave_length_2) - t * (2 * np.pi * wave_speed / wave_length_2) + np.pi/3  # Phase offset
        phase_3 = (x * wave_dir_3[0] + y * wave_dir_3[1]) * (2 * np.pi / wave_length_3) - t * (2 * np.pi * wave_speed / wave_length_3) + np.pi/2  # Different phase
        
        # Calculate wave amplitudes
        wave_1 = np.sin(phase_1) * 0.4
        wave_2 = np.sin(phase_2) * 0.3
        wave_3 = np.sin(phase_3) * 0.2
        
        # Combine waves
        combined_wave = wave_1 + wave_2 + wave_3
        
        # Normalize to 0-1 range for intensity
        wave_intensity = (combined_wave + 1.0) / 2.0  # Convert from [-1,1] to [0,1]
        
        # Apply some smoothing/contrast
        wave_intensity = np.power(wave_intensity, 1.5)  # Increase contrast
        wave_intensity = np.clip(wave_intensity, 0, 1)
        
        # Lightness varies with wave amplitude
        base_lightness = 0.1
        oklch_output[:, 0] = base_lightness + wave_intensity * 0.8
        
        # Chroma varies with wave intensity
        base_chroma = 0.05
        oklch_output[:, 1] = base_chroma + wave_intensity * 0.35
        
        # Hue shifts with wave phase and time
        # Use the primary wave phase for hue calculation
        hue_base = t * 40.0  # Base rotation
        hue_wave = np.degrees(phase_1) * 0.5  # Wave phase affects hue
        hue_intensity = wave_intensity * 120.0  # Intensity shifts hue
        oklch_output[:, 2] = (hue_base + hue_wave + hue_intensity) % 360.0
        
        return oklch_output