"""Tunnel Vision pattern with concentric shapes racing toward center."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class TunnelVisionPattern(LuminaryPattern):
    """Concentric shapes racing toward the center creating tunnel effect."""
    
    def __init__(self):
        # Randomize initial direction
        import random
        self.initial_direction_offset = random.randint(0, 1)  # 0 or 1
    
    @property
    def name(self) -> str:
        return "Tunnel Vision"
    
    @property
    def description(self) -> str:
        return "Concentric shapes racing toward center creating hypnotic tunnel effect"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate tunnel vision pattern with inward-moving concentric shapes."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract spatial coordinates
        x = beam_array[:, BeamArrayColumns.X]
        y = beam_array[:, BeamArrayColumns.Y] 
        
        # Find the center of the empty pentagon (the dark hole in the geometry)
        # Looking at the image, the pentagon is positioned lower than the top edge
        # and slightly left of geometric center
        
        # Estimate pentagon position based on observed geometry
        coord_range_x = np.max(x) - np.min(x)
        coord_range_y = np.max(y) - np.min(y)
        
        # Pentagon appears to be down from the top, centered horizontally
        center_x = np.mean(x)  # No horizontal offset
        center_y = np.max(y) - coord_range_y * 0.375  # 15% + 1.5 * 15% = 37.5% down from top
        
        # Calculate distance from tunnel center
        r = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        
        # Debug: Check coordinate ranges
        max_r = np.max(r)
        
        # Tunnel parameters - adjusted for actual coordinate scale
        tunnel_speed = 25.0    # Speed of ring movement
        ring_spacing = 35.0    # Distance between rings  
        ring_width = 15.0      # Ring thickness
        num_rings = 12         # More rings for continuous flow
        max_radius = max_r * 1.2  # Boundary for ring spawning
        
        # Global direction switching - changes every 60 seconds with random initial direction
        direction_cycle = 60.0  # Seconds per direction (much longer for immersive experience)
        direction_phase = int(t / direction_cycle) + self.initial_direction_offset
        going_inward = (direction_phase % 2) == 0  # Flip every 60 seconds, randomized start
        
        # Create infinite flow of rings - ALL move in same direction
        total_intensity = np.zeros_like(r)
        
        for ring_idx in range(num_rings):
            if going_inward:
                # ALL rings move from outside toward center
                ring_offset = (t * tunnel_speed + ring_idx * ring_spacing) % (num_rings * ring_spacing)
                ring_radius = max_radius - ring_offset
                # Wrap around when ring reaches center
                if ring_radius < 0:
                    ring_radius += num_rings * ring_spacing
            else:
                # ALL rings move from center toward outside
                ring_offset = (t * tunnel_speed + ring_idx * ring_spacing) % (num_rings * ring_spacing)
                ring_radius = ring_offset - max_radius * 0.3
                # Wrap around when ring reaches edge
                if ring_radius > max_radius:
                    ring_radius -= num_rings * ring_spacing
            
            # Show rings that are in visible range
            if ring_radius > -ring_spacing and ring_radius < max_radius + ring_spacing:
                # Distance from current ring position
                distance_from_ring = np.abs(r - ring_radius)
                
                # Ring intensity (Gaussian falloff)
                ring_intensity = np.exp(-distance_from_ring**2 / (ring_width**2))
                
                # Fade based on distance from center (tunnel depth effect)
                if going_inward:
                    # Inward: fade as approaching center
                    center_fade = np.clip(ring_radius / (max_r * 0.4), 0.2, 1.0)
                else:
                    # Outward: fade as moving away from center
                    center_fade = np.clip((max_radius - ring_radius) / (max_r * 0.4), 0.2, 1.0)
                
                ring_intensity *= center_fade
                
                # Add pulsing variation to rings
                ring_variation = 0.7 + 0.5 * np.sin(ring_idx * 1.8 + t * 2.0)
                ring_intensity *= ring_variation
                
                total_intensity += ring_intensity
        
        # Clamp intensity
        total_intensity = np.clip(total_intensity, 0, 1)
        
        # Create psychedelic tunnel colors
        # Lightness: dark background with bright rings
        base_lightness = 0.08  # Dark space
        oklch_output[:, 0] = base_lightness + 0.7 * total_intensity
        
        # Chroma: high saturation for trippy effect
        oklch_output[:, 1] = 0.1 + 0.35 * total_intensity
        
        # Hue: rainbow spectrum based on distance from center + time
        # Inner rings are cooler colors, outer rings are warmer
        hue_base = (r * 0.8 + t * 60.0) % 360.0  # Rotating rainbow
        
        # Add intensity-based hue shifting (bright parts get different colors)
        hue_shift = total_intensity * 120.0  # Shift hue based on ring intensity
        oklch_output[:, 2] = (hue_base + hue_shift) % 360.0
        
        # Apply colors only where there's significant intensity
        visible = total_intensity > 0.05
        oklch_output[~visible, 0] = 0.02  # Very dark background
        oklch_output[~visible, 1] = 0.0   # No chroma in dark areas
        
        return oklch_output