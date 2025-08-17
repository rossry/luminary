"""Plasma Storm pattern with multi-layered sine wave interference creating electric effects."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class LightningBolt:
    """A jagged lightning bolt that flashes across the pattern."""
    path: List[Tuple[float, float]]  # List of (x, y) points forming the jagged path
    spawn_time: float  # When the bolt was created
    duration: float    # How long the bolt lasts
    intensity: float   # Peak brightness of the bolt
    width: float       # Thickness of the lightning stroke


class PlasmaStormPattern(LuminaryPattern):
    """Electric plasma storm with multi-layered sine wave interference patterns."""
    
    def __init__(self):
        # Randomize some parameters each time for variety
        import random
        self.rng = random.Random(random.randint(0, 1000000))
        
        # Random phase offsets for interference patterns
        self.phase_offsets = [self.rng.uniform(0, 2*np.pi) for _ in range(8)]
        
        # Random frequency multipliers for different plasma layers
        self.freq_multipliers = [self.rng.uniform(0.8, 2.5) for _ in range(6)]
        
        # Lightning bolt system
        self.lightning_bolts = []
        self.last_bolt_time = 0.0
        
    @property
    def name(self) -> str:
        return "Plasma Storm"
    
    @property
    def description(self) -> str:
        return "Electric plasma storm with high-contrast lightning-like interference patterns"
    
    def _should_spawn_lightning(self, t: float) -> bool:
        """Decide if a new lightning bolt should spawn using Poisson distribution."""
        # Use Poisson distribution with mean interval of 4 seconds (0-8 second range)
        # This allows for both rapid succession and longer pauses
        mean_interval = 4.0
        lambda_rate = 1.0 / mean_interval
        
        # Check if enough time has passed since last bolt
        time_since_last = t - self.last_bolt_time
        
        # Use exponential distribution (equivalent to Poisson timing)
        # Generate next interval using inverse transform sampling
        next_interval = -np.log(self.rng.random()) / lambda_rate
        
        # Allow minimum interval of 0.1 seconds to prevent frame-rate issues
        next_interval = max(next_interval, 0.1)
        
        return time_since_last >= next_interval
    
    def _generate_jagged_path(self, start_x: float, start_y: float, end_x: float, end_y: float, 
                            segments: int = 8) -> List[Tuple[float, float]]:
        """Generate a jagged lightning bolt path between two points."""
        path = [(start_x, start_y)]
        
        for i in range(1, segments):
            # Linear interpolation for base position
            t = i / segments
            base_x = start_x + t * (end_x - start_x)
            base_y = start_y + t * (end_y - start_y)
            
            # Add jagged deviation
            max_deviation = 0.15  # Max deviation as fraction of total distance
            total_dist = np.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
            deviation = self.rng.uniform(-max_deviation, max_deviation) * total_dist
            
            # Perpendicular direction for deviation
            perp_x = -(end_y - start_y) / total_dist if total_dist > 0 else 0
            perp_y = (end_x - start_x) / total_dist if total_dist > 0 else 0
            
            # Apply jagged deviation
            jagged_x = base_x + deviation * perp_x
            jagged_y = base_y + deviation * perp_y
            
            path.append((jagged_x, jagged_y))
        
        path.append((end_x, end_y))
        return path
    
    def _spawn_lightning_bolt(self, t: float, x_range: tuple, y_range: tuple) -> None:
        """Create a new lightning bolt with random path."""
        # Random start and end points
        start_x = self.rng.uniform(x_range[0], x_range[1])
        start_y = self.rng.uniform(y_range[0], y_range[1])
        end_x = self.rng.uniform(x_range[0], x_range[1])
        end_y = self.rng.uniform(y_range[0], y_range[1])
        
        # Generate jagged path
        segments = self.rng.randint(6, 12)  # Random complexity
        path = self._generate_jagged_path(start_x, start_y, end_x, end_y, segments)
        
        # Lightning properties
        duration = self.rng.uniform(0.15, 0.4)  # Very brief flash
        intensity = self.rng.uniform(0.8, 1.0)  # Very bright
        width = self.rng.uniform(0.02, 0.05)    # Thin but visible
        
        bolt = LightningBolt(
            path=path,
            spawn_time=t,
            duration=duration,
            intensity=intensity,
            width=width
        )
        
        self.lightning_bolts.append(bolt)
        self.last_bolt_time = t
    
    def _update_lightning_bolts(self, t: float) -> None:
        """Remove expired lightning bolts."""
        self.lightning_bolts = [bolt for bolt in self.lightning_bolts 
                              if t - bolt.spawn_time < bolt.duration]
    
    def _render_lightning_intensity(self, x_norm: np.ndarray, y_norm: np.ndarray, t: float) -> np.ndarray:
        """Calculate lightning bolt contribution to pixel intensity."""
        lightning_intensity = np.zeros_like(x_norm)
        
        for bolt in self.lightning_bolts:
            # Calculate flash intensity based on time
            bolt_age = t - bolt.spawn_time
            flash_progress = bolt_age / bolt.duration
            
            # Double flash effect - two distinct peaks with sharp falloff
            # First flash at 15% of duration, second at 70% of duration  
            flash1 = np.exp(-((flash_progress - 0.15) / 0.10)**2)  # Slightly longer first flash
            flash2 = np.exp(-((flash_progress - 0.70) / 0.08)**2)  # Sharp second flash
            flash_intensity = (flash1 + flash2) * bolt.intensity
            
            if flash_intensity > 0.01:  # Only render if visible
                # Calculate distance from bolt path for each LED
                for i in range(len(bolt.path) - 1):
                    x1, y1 = bolt.path[i]
                    x2, y2 = bolt.path[i + 1]
                    
                    # Distance from line segment
                    line_intensity = self._distance_from_line_segment(
                        x_norm, y_norm, x1, y1, x2, y2, bolt.width
                    )
                    
                    lightning_intensity += line_intensity * flash_intensity
        
        return np.clip(lightning_intensity, 0, 1)
    
    def _distance_from_line_segment(self, px: np.ndarray, py: np.ndarray, 
                                  x1: float, y1: float, x2: float, y2: float, 
                                  width: float) -> np.ndarray:
        """Calculate intensity based on distance from a line segment."""
        # Vector from start to end of line
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx*dx + dy*dy
        
        if length_sq == 0:
            # Degenerate case - line is a point
            dist = np.sqrt((px - x1)**2 + (py - y1)**2)
        else:
            # Project point onto line segment
            t = np.clip(((px - x1) * dx + (py - y1) * dy) / length_sq, 0, 1)
            
            # Find closest point on line segment
            closest_x = x1 + t * dx
            closest_y = y1 + t * dy
            
            # Distance from point to closest point on line
            dist = np.sqrt((px - closest_x)**2 + (py - closest_y)**2)
        
        # Convert distance to intensity (sharp falloff for thin lightning)
        return np.exp(-(dist**2) / (width**2))
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate plasma storm pattern with layered sine wave interference."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract spatial coordinates
        x = beam_array[:, BeamArrayColumns.X]
        y = beam_array[:, BeamArrayColumns.Y]
        
        # Normalize coordinates for consistent patterns across different geometries
        x_range = np.max(x) - np.min(x)
        y_range = np.max(y) - np.min(y)
        x_norm = (x - np.min(x)) / x_range if x_range > 0 else x
        y_norm = (y - np.min(y)) / y_range if y_range > 0 else y
        
        # Lightning bolt management
        self._update_lightning_bolts(t)
        if self._should_spawn_lightning(t):
            self._spawn_lightning_bolt(t, (0.0, 1.0), (0.0, 1.0))  # Normalized coordinate range
        
        # Create multiple plasma layers with different frequencies and phases
        plasma_intensity = np.zeros_like(x_norm)
        
        # Layer 1: High-frequency horizontal waves (lightning streaks)
        freq1 = 8.0 * self.freq_multipliers[0]
        phase1 = t * 3.0 + self.phase_offsets[0]
        wave1 = np.sin(y_norm * freq1 + phase1) * np.cos(x_norm * freq1 * 0.3 + phase1 * 1.2)
        plasma_intensity += 0.4 * wave1
        
        # Layer 2: Vertical interference patterns
        freq2 = 6.0 * self.freq_multipliers[1]
        phase2 = t * 2.2 + self.phase_offsets[1]
        wave2 = np.sin(x_norm * freq2 + phase2) * np.cos(y_norm * freq2 * 0.7 + phase2 * 0.8)
        plasma_intensity += 0.3 * wave2
        
        # Layer 3: Diagonal interference (creates X patterns)
        freq3 = 5.0 * self.freq_multipliers[2]
        phase3 = t * 1.8 + self.phase_offsets[2]
        diagonal1 = (x_norm + y_norm) * freq3 + phase3
        diagonal2 = (x_norm - y_norm) * freq3 + phase3 * 1.3
        wave3 = np.sin(diagonal1) * np.sin(diagonal2)
        plasma_intensity += 0.35 * wave3
        
        # Layer 4: Radial waves from center
        center_x = np.mean(x_norm)
        center_y = np.mean(y_norm)
        r_norm = np.sqrt((x_norm - center_x)**2 + (y_norm - center_y)**2)
        freq4 = 12.0 * self.freq_multipliers[3]
        phase4 = t * 4.5 + self.phase_offsets[3]
        wave4 = np.sin(r_norm * freq4 + phase4)
        plasma_intensity += 0.25 * wave4
        
        # Layer 5: Fast chaotic interference
        freq5 = 15.0 * self.freq_multipliers[4]
        phase5 = t * 6.0 + self.phase_offsets[4]
        chaos_x = np.sin(x_norm * freq5 + phase5) * np.cos(y_norm * freq5 * 1.4 + phase5 * 0.6)
        chaos_y = np.cos(x_norm * freq5 * 0.8 + phase5 * 1.7) * np.sin(y_norm * freq5 + phase5 * 0.3)
        wave5 = chaos_x + chaos_y
        plasma_intensity += 0.2 * wave5
        
        # Layer 6: Slow background modulation
        freq6 = 2.0 * self.freq_multipliers[5]
        phase6 = t * 0.7 + self.phase_offsets[5]
        background = np.sin(x_norm * freq6 + phase6) * np.cos(y_norm * freq6 + phase6 * 1.5)
        plasma_intensity += 0.15 * background
        
        # Normalize and enhance contrast
        plasma_intensity = (plasma_intensity + 1.0) / 2.0  # Map from [-1,1] to [0,1]
        
        # Apply high contrast transformation - make it more black and white
        contrast_power = 3.0
        plasma_intensity = np.power(plasma_intensity, contrast_power)
        
        # Create "lightning bolt" areas - sharp peaks become very bright
        lightning_threshold = 0.7
        lightning_boost = np.where(plasma_intensity > lightning_threshold, 
                                 (plasma_intensity - lightning_threshold) * 8.0, 0)
        plasma_intensity += lightning_boost
        
        # Clamp to [0,1]
        plasma_intensity = np.clip(plasma_intensity, 0, 1)
        
        # Add lightning bolt intensity
        lightning_intensity = self._render_lightning_intensity(x_norm, y_norm, t)
        
        # Combine plasma and lightning (lightning overrides plasma in bright areas)
        combined_intensity = np.maximum(plasma_intensity, lightning_intensity)
        
        # Create dramatic black and white with color highlights
        
        # Lightness: Strong contrast - either very dark or very bright
        base_lightness = 0.02  # Deep black background
        bright_areas = combined_intensity > 0.3
        
        # Most areas stay dark, bright areas become very bright
        oklch_output[:, 0] = base_lightness
        oklch_output[bright_areas, 0] = 0.1 + combined_intensity[bright_areas] * 0.85
        
        # Chroma: High saturation for electric colors, but only in active areas
        oklch_output[:, 1] = 0.0  # Start with no chroma
        electric_areas = combined_intensity > 0.5
        oklch_output[electric_areas, 1] = 0.15 + combined_intensity[electric_areas] * 0.3
        
        # Hue: Electric blues and purples with some variation
        base_hue = 240.0  # Electric blue
        
        # Add spatial hue variation for more complex colors
        hue_variation1 = 60.0 * np.sin(x_norm * 3.0 + t * 0.5)  # Slow hue waves
        hue_variation2 = 30.0 * np.sin(y_norm * 4.0 + t * 0.8)  # Cross waves
        
        # Areas with high plasma get electric blue/purple, others get slight variation
        hue = (base_hue + hue_variation1 + hue_variation2 + 
               combined_intensity * 90.0) % 360.0  # Intensity shifts hue
        
        oklch_output[:, 2] = hue
        
        # Lightning bolts get special white treatment
        pure_lightning = lightning_intensity > 0.3
        oklch_output[pure_lightning, 0] = 0.95  # Brilliant white lightning
        oklch_output[pure_lightning, 1] = 0.05  # Very low chroma = pure white
        
        # Regular bright areas get electric color treatment
        bright_plasma = (combined_intensity > 0.85) & (lightning_intensity < 0.3)
        oklch_output[bright_plasma, 0] = 0.9   # Very bright but not white
        oklch_output[bright_plasma, 1] = 0.25  # Keep electric color
        
        return oklch_output