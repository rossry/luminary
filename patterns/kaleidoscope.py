"""Kaleidoscope pattern with radially symmetric rotating geometric shapes."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class KaleidoscopePattern(LuminaryPattern):
    """Radially symmetric pattern with rotating, reflecting geometric shapes."""
    
    @property
    def name(self) -> str:
        return "Kaleidoscope"
    
    @property
    def description(self) -> str:
        return "Radially symmetric rotating geometric shapes like looking through a kaleidoscope"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate kaleidoscope pattern with radial symmetry."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract spatial coordinates
        x = beam_array[:, BeamArrayColumns.X]
        y = beam_array[:, BeamArrayColumns.Y]
        
        # Center the coordinates
        center_x = np.mean(x)
        center_y = np.mean(y)
        
        # Convert to polar coordinates centered on the pattern
        dx = x - center_x
        dy = y - center_y
        r = np.sqrt(dx**2 + dy**2)
        theta = np.arctan2(dy, dx)  # Angle from center
        
        # Kaleidoscope parameters
        num_segments = 6  # Number of mirror segments (hexagonal symmetry)
        rotation_speed = 0.3  # Radians per second
        
        # Apply rotation over time
        theta_rotated = theta + t * rotation_speed
        
        # Create kaleidoscope symmetry by folding angles
        segment_angle = 2 * np.pi / num_segments
        
        # Fold theta to create mirror symmetry within each segment
        theta_folded = np.abs((theta_rotated % segment_angle) - segment_angle/2)
        
        # Convert back to cartesian for pattern generation
        x_sym = r * np.cos(theta_folded)
        y_sym = r * np.sin(theta_folded)
        
        # Generate base patterns - multiple overlapping shapes
        total_intensity = np.zeros_like(r)
        
        # Pattern 1: Radial stripes
        stripe_pattern = np.sin(theta_folded * 8 + t * 2.0) * 0.5 + 0.5
        stripe_intensity = np.exp(-(r - 50)**2 / 800) * stripe_pattern
        total_intensity += 0.4 * stripe_intensity
        
        # Pattern 2: Concentric circles with radial modulation
        for circle_idx in range(4):
            circle_radius = 30 + circle_idx * 25
            circle_thickness = 8
            
            # Distance from circle
            circle_dist = np.abs(r - circle_radius)
            circle_intensity = np.exp(-circle_dist**2 / (circle_thickness**2))
            
            # Modulate with angular position
            angular_mod = np.sin(theta_folded * (3 + circle_idx) + t * (1.5 + circle_idx * 0.5))
            circle_intensity *= (0.6 + 0.4 * angular_mod)
            
            total_intensity += 0.3 * circle_intensity
        
        # Pattern 3: Triangular/diamond shapes
        # Create triangular pattern using the folded coordinates
        triangle_pattern1 = np.sin(x_sym * 0.08 + t * 1.2) * np.cos(y_sym * 0.06 + t * 0.8)
        triangle_pattern2 = np.sin(x_sym * 0.05 + y_sym * 0.07 + t * 1.8)
        
        triangle_intensity = (triangle_pattern1 + triangle_pattern2) * 0.5 + 0.5
        # Apply radial falloff
        triangle_intensity *= np.exp(-r / 100.0)
        
        total_intensity += 0.5 * triangle_intensity
        
        # Pattern 4: Center star burst
        star_burst = np.exp(-r / 20.0) * (np.sin(theta_folded * 12 + t * 3.0) * 0.5 + 0.5)
        total_intensity += 0.6 * star_burst
        
        # Clamp total intensity
        total_intensity = np.clip(total_intensity, 0, 1)
        
        # Color generation
        # Lightness: varies with pattern intensity
        base_lightness = 0.1
        oklch_output[:, 0] = base_lightness + 0.6 * total_intensity
        
        # Chroma: high saturation for vibrant kaleidoscope colors
        oklch_output[:, 1] = 0.05 + 0.4 * total_intensity
        
        # Hue: creates rainbow segments that rotate
        # Each mirror segment gets a different base hue
        segment_hue = (theta_rotated / segment_angle) * 60.0  # 60° per segment
        
        # Add radial hue variation and time-based shifting
        radial_hue_shift = r * 0.5  # Hue changes with distance from center
        time_hue_shift = t * 30.0    # Slow hue rotation over time
        
        hue = (segment_hue + radial_hue_shift + time_hue_shift + 
               total_intensity * 90.0) % 360.0  # Intensity affects hue
        
        oklch_output[:, 2] = hue
        
        # Apply minimum brightness to dark areas for ambiance
        dark_areas = total_intensity < 0.1
        oklch_output[dark_areas, 0] = np.maximum(oklch_output[dark_areas, 0], 0.02)
        oklch_output[dark_areas, 1] = 0.01  # Very low chroma in dark areas
        
        return oklch_output