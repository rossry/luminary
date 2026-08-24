"""V2 - Multiple lamps roaming around with angular-based hue gradients."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class RoamingLamps2(Pattern):
    """V2 - Multiple lamps roaming around with angular-based hue gradients."""

    name = "roaming_lamps_2"
    description = "Moving lamps with hue based on viewing angle and unique palettes"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Extract coordinates
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        r = lights[:, LightColumns.R]

        # lamp parameters
        num_lamps = 6
        move_speed = 0.7  # Radians per second for angular motion
        min_radius = 5.0  # Minimum distance from center
        max_radius = 180.0  # Maximum distance from center
        gradient_size = 50.0  # How far the gradient extends

        # Define color palettes for each lamp (hue ranges)
        palettes = [
            {"base": 0, "range": 60},  # Red to yellow
            {"base": 120, "range": 60},  # Green to cyan
            {"base": 240, "range": 60},  # Blue to magenta
            {"base": 60, "range": 40},  # Yellow to orange
            {"base": 300, "range": 50},  # Magenta to red
            {"base": 180, "range": 70},  # Cyan to blue
        ]

        # Initialize intensity and hue arrays
        total_intensity = np.zeros_like(r)
        weighted_hue = np.zeros_like(r)
        total_weight = np.zeros_like(r)

        # Create roaming lamps (bounded loop over 6 lamps)
        for lamp_idx in range(num_lamps):
            # Each lamp gets different motion parameters
            lamp_phase = lamp_idx * (2 * np.pi / num_lamps)

            # Radial motion (oscillating between min and max radius)
            radial_freq = 0.4 + lamp_idx * 0.1
            lamp_r = min_radius + (max_radius - min_radius) * (
                0.5 + 0.5 * np.sin(t * radial_freq + lamp_phase)
            )

            # Angular motion (rotating around, with some wobble)
            direction = 1 if lamp_idx % 2 == 0 else -1
            angular_freq = move_speed * (0.8 + lamp_idx * 0.3) * direction
            angular_wobble = 0.5 * np.sin(t * (radial_freq * 2) + lamp_phase * 1.7)
            lamp_theta = (t * angular_freq + lamp_phase + angular_wobble) % (2 * np.pi)

            # Convert lamp to Cartesian coordinates
            lamp_x = lamp_r * np.cos(lamp_theta)
            lamp_y = lamp_r * np.sin(lamp_theta)

            # Calculate distance from each beam to this lamp
            dx = x - lamp_x
            dy = y - lamp_y
            total_dist = np.sqrt(dx**2 + dy**2)

            # Create intensity based on distance
            lamp_intensity = np.exp(-total_dist / gradient_size)

            # Calculate angle from lamp to each beam position
            angle_to_beam = np.arctan2(dy, dx)  # Returns -pi to pi

            # Get this lamp's palette
            palette = palettes[lamp_idx % len(palettes)]
            palette_base = palette["base"]
            palette_range = palette["range"]

            # Create a mirrored gradient using sine to avoid discontinuity
            time_rotation = t * 30  # No modulo, for smoother rotation
            angle_with_time = angle_to_beam + np.radians(time_rotation)

            # Use absolute sine to create a mirrored gradient
            hue_oscillation = np.abs(np.sin(angle_with_time)) * 10

            lamp_hue = (palette_base + hue_oscillation * palette_range) % 360

            # Add this lamp's contribution
            total_intensity += lamp_intensity

            # Weight the hue by intensity for proper color mixing
            weighted_hue += lamp_hue * lamp_intensity
            total_weight += lamp_intensity

        # Avoid division by zero
        total_weight = np.maximum(total_weight, 1e-6)

        # Calculate final hue (weighted average)
        final_hue = weighted_hue / total_weight

        # Clamp total intensity
        total_intensity = np.clip(total_intensity, 0, 2.0)

        # Set OKLCH values
        base_lightness = 0.05
        oklch_output[:, 0] = np.clip(base_lightness + total_intensity * 0.75, 0.0, 1.0)

        base_chroma = 0.02
        # chroma_contrast rescaled from 0.2 so peak chroma stays within 0.4
        oklch_output[:, 1] = np.clip(base_chroma + total_intensity * 0.185, 0.0, 0.4)

        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
