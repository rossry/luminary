"""Bouncing stick figure nudes pattern."""

import numpy as np
from typing import List
from dataclasses import dataclass
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


@dataclass
class StickFigure:
    """A stick figure that bounces around in 2D space."""
    # Position and velocity
    x: float
    y: float
    vx: float
    vy: float
    
    # Visual properties
    scale: float  # Size multiplier
    hue: float    # Color hue
    brightness: float  # Brightness multiplier
    rotation: float  # Orientation angle in radians
    
    # Animation state
    bounce_phase: float  # For bouncy animation effects


class BouncingNudesPattern(LuminaryPattern):
    """Stick figure nudes bouncing around the sphere."""
    
    @property
    def name(self) -> str:
        return "Bouncing Nudes"
    
    @property
    def description(self) -> str:
        return "Playful stick figure nudes bouncing around in 2D space"
    
    def __init__(self):
        # Create 2 stick figures with different properties
        self.figures: List[StickFigure] = []
        
        # RNG for consistent randomness
        self.rng = np.random.default_rng(69)  # Nice
        
        # Coordinate bounds (will be set based on actual LED positions)
        self.bounds = {'x_min': -250, 'x_max': 250, 'y_min': -150, 'y_max': 100}
        
        # Create initial figures
        self._spawn_figures()
    
    def _spawn_figures(self) -> None:
        """Create initial stick figures."""
        for i in range(2):
            # Random starting positions
            x = self.rng.uniform(self.bounds['x_min'] * 0.8, self.bounds['x_max'] * 0.8)
            y = self.rng.uniform(self.bounds['y_min'] * 0.8, self.bounds['y_max'] * 0.8)
            
            # Random velocities (bouncy speed)
            vx = self.rng.uniform(-60, 60)
            vy = self.rng.uniform(-60, 60)
            
            # Visual properties
            scale = self.rng.uniform(0.8, 1.5)
            hue = self.rng.uniform(0, 360)
            brightness = self.rng.uniform(0.7, 1.0)
            rotation = self.rng.uniform(0, 2 * np.pi)  # Random starting orientation
            bounce_phase = self.rng.uniform(0, 2 * np.pi)
            
            figure = StickFigure(
                x=x, y=y, vx=vx, vy=vy,
                scale=scale, hue=hue, brightness=brightness, rotation=rotation,
                bounce_phase=bounce_phase
            )
            
            self.figures.append(figure)
    
    def _update_figures(self, dt: float) -> None:
        """Update figure positions and handle bouncing."""
        for figure in self.figures:
            # Update position
            figure.x += figure.vx * dt
            figure.y += figure.vy * dt
            
            # Bounce off walls with some randomness
            if figure.x <= self.bounds['x_min'] or figure.x >= self.bounds['x_max']:
                figure.vx *= -0.8  # Some energy loss
                figure.vx += self.rng.uniform(-10, 10)  # Add randomness
                figure.x = np.clip(figure.x, self.bounds['x_min'], self.bounds['x_max'])
                
            if figure.y <= self.bounds['y_min'] or figure.y >= self.bounds['y_max']:
                figure.vy *= -0.8  # Some energy loss  
                figure.vy += self.rng.uniform(-10, 10)  # Add randomness
                figure.y = np.clip(figure.y, self.bounds['y_min'], self.bounds['y_max'])
            
            # Update bounce phase for animation
            figure.bounce_phase += dt * 4.0
            
            # Slowly rotate the figure over time
            figure.rotation += dt * 0.5  # Gentle continuous rotation
            
            # Occasionally change color
            if self.rng.random() < 0.002:  # 0.2% chance per frame
                figure.hue = self.rng.uniform(0, 360)
    
    def _rotate_point(self, x: float, y: float, cx: float, cy: float, angle: float) -> tuple[float, float]:
        """Rotate a point around a center point."""
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        # Translate to origin
        dx = x - cx
        dy = y - cy
        
        # Rotate
        rotated_x = dx * cos_a - dy * sin_a
        rotated_y = dx * sin_a + dy * cos_a
        
        # Translate back
        return cx + rotated_x, cy + rotated_y
    
    def _draw_stick_figure(self, led_x: np.ndarray, led_y: np.ndarray, figure: StickFigure, t: float) -> np.ndarray:
        """Draw a stick figure and return intensity values for each LED."""
        n_beams = len(led_x)
        intensity = np.zeros(n_beams, dtype=np.float32)
        
        # Figure dimensions (scaled)
        scale = figure.scale
        head_radius = 15 * scale
        body_height = 60 * scale
        arm_length = 40 * scale
        leg_length = 50 * scale
        line_width = 8 * scale
        
        # Bouncy animation offset
        bounce_offset = 5 * scale * np.sin(figure.bounce_phase)
        
        # Figure center position (with bounce)
        fx = figure.x
        fy = figure.y + bounce_offset
        
        # Body parts positions (before rotation)
        head_x_base, head_y_base = fx, fy + body_height/2 + head_radius
        body_top_x_base, body_top_y_base = fx, fy + body_height/2
        body_bottom_x_base, body_bottom_y_base = fx, fy - body_height/2
        
        # Arms (with slight animation, before rotation)
        arm_angle = 0.3 * np.sin(t * 3 + figure.bounce_phase)
        left_arm_x_base = fx - arm_length * np.cos(arm_angle)
        left_arm_y_base = fy + body_height/4 + arm_length * np.sin(arm_angle)
        right_arm_x_base = fx + arm_length * np.cos(arm_angle)  
        right_arm_y_base = fy + body_height/4 - arm_length * np.sin(arm_angle)
        
        # Legs (with walking animation, before rotation)
        leg_angle = 0.4 * np.sin(t * 4 + figure.bounce_phase)
        left_leg_x_base = fx - leg_length * np.sin(leg_angle)
        left_leg_y_base = fy - body_height/2 - leg_length * np.cos(leg_angle)
        right_leg_x_base = fx + leg_length * np.sin(leg_angle)
        right_leg_y_base = fy - body_height/2 - leg_length * np.cos(leg_angle)
        
        # Apply rotation to all body parts around figure center
        head_x, head_y = self._rotate_point(head_x_base, head_y_base, fx, fy, figure.rotation)
        body_top_x, body_top_y = self._rotate_point(body_top_x_base, body_top_y_base, fx, fy, figure.rotation)
        body_bottom_x, body_bottom_y = self._rotate_point(body_bottom_x_base, body_bottom_y_base, fx, fy, figure.rotation)
        left_arm_x, left_arm_y = self._rotate_point(left_arm_x_base, left_arm_y_base, fx, fy, figure.rotation)
        right_arm_x, right_arm_y = self._rotate_point(right_arm_x_base, right_arm_y_base, fx, fy, figure.rotation)
        left_leg_x, left_leg_y = self._rotate_point(left_leg_x_base, left_leg_y_base, fx, fy, figure.rotation)
        right_leg_x, right_leg_y = self._rotate_point(right_leg_x_base, right_leg_y_base, fx, fy, figure.rotation)
        
        # Draw each body part using distance from lines/circles
        
        # Head (circle)
        head_dist = np.sqrt((led_x - head_x)**2 + (led_y - head_y)**2)
        head_intensity = np.exp(-np.maximum(0, head_dist - head_radius)**2 / (line_width**2))
        intensity += head_intensity
        
        # Body (vertical line)
        body_intensity = self._line_intensity(led_x, led_y, body_top_x, body_top_y, body_bottom_x, body_bottom_y, line_width)
        intensity += body_intensity
        
        # Left arm
        left_arm_intensity = self._line_intensity(led_x, led_y, body_top_x, body_top_y, left_arm_x, left_arm_y, line_width)
        intensity += left_arm_intensity
        
        # Right arm  
        right_arm_intensity = self._line_intensity(led_x, led_y, body_top_x, body_top_y, right_arm_x, right_arm_y, line_width)
        intensity += right_arm_intensity
        
        # Left leg
        left_leg_intensity = self._line_intensity(led_x, led_y, body_bottom_x, body_bottom_y, left_leg_x, left_leg_y, line_width)
        intensity += left_leg_intensity
        
        # Right leg
        right_leg_intensity = self._line_intensity(led_x, led_y, body_bottom_x, body_bottom_y, right_leg_x, right_leg_y, line_width)
        intensity += right_leg_intensity
        
        # Clamp and return
        return np.clip(intensity, 0, 1)
    
    def _line_intensity(self, px: np.ndarray, py: np.ndarray, x1: float, y1: float, x2: float, y2: float, width: float) -> np.ndarray:
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
        
        # Convert distance to intensity (Gaussian falloff)
        return np.exp(-(dist**2) / (width**2))
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate bouncing stick figure pattern."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)
        
        # Extract LED positions
        led_x = beam_array[:, BeamArrayColumns.X]
        led_y = beam_array[:, BeamArrayColumns.Y]
        
        # Update coordinate bounds based on actual LED positions
        self.bounds = {
            'x_min': float(np.min(led_x)),
            'x_max': float(np.max(led_x)),
            'y_min': float(np.min(led_y)), 
            'y_max': float(np.max(led_y))
        }
        
        # Update figures
        dt = 0.033  # ~30 FPS
        self._update_figures(dt)
        
        # Start with black background
        oklch_output[:, 0] = 0.05  # Very dim
        oklch_output[:, 1] = 0.0   # No chroma
        oklch_output[:, 2] = 0.0   # Hue doesn't matter
        
        # Draw each stick figure
        for figure in self.figures:
            intensity = self._draw_stick_figure(led_x, led_y, figure, t)
            
            # Apply color where figure is visible
            visible = intensity > 0.1
            
            if np.any(visible):
                # Lightness increases with intensity
                oklch_output[visible, 0] = np.clip(0.3 + intensity[visible] * 0.6 * figure.brightness, 0, 1)
                
                # Chroma for visible parts
                oklch_output[visible, 1] = np.clip(0.25 + intensity[visible] * 0.15, 0, 0.4)
                
                # Hue from figure properties
                oklch_output[visible, 2] = figure.hue
        
        return oklch_output