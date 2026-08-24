"""Multiple lamps roaming around with rainbow gradient halos."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class RoamingLamps1(Pattern):
    """Multiple lamps roaming around with rainbow gradient halos in polar space."""

    name = "roaming_lamps_1"
    description = "Moving lamps with rainbow gradient halos"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Extract polar coordinates
        r = lights[:, LightColumns.R]
        theta = lights[:, LightColumns.THETA]

        # lamp parameters
        num_lamps = 6
        move_speed = 0.7  # Radians per second for angular motion
        min_radius = 5.0  # Minimum distance from center
        max_radius = 180.0  # Maximum distance from center
        gradient_size = 50.0  # How far the gradient extends

        # Initialize intensity and hue arrays
        total_intensity = np.zeros_like(r)
        weighted_hue = np.zeros_like(r)
        total_weight = np.zeros_like(r)

        # Create roaming lamps in polar space (bounded loop over 6 lamps)
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

            # Distance from each beam to this lamp in polar space.
            # Radial distance component
            radial_dist = np.abs(r - lamp_r)

            # Angular distance component (shortest path around the circle)
            angular_diff = np.abs(theta - lamp_theta)
            angular_diff = np.minimum(angular_diff, 2 * np.pi - angular_diff)

            # Convert angular difference to arc length at the beam's radius
            # This makes the gradient size consistent regardless of radius
            angular_dist = r * angular_diff

            # Total distance in polar space (radial vs angular components)
            total_dist = np.sqrt(radial_dist**2 + angular_dist**2)

            # Create intensity based on distance
            lamp_intensity = np.exp(-total_dist / gradient_size)

            # Each lamp gets a different base hue that shifts over time
            lamp_base_hue = (lamp_idx * 60 + t * 25) % 360

            # Hue shifts based on distance and angle for rainbow effect
            distance_hue_shift = (total_dist / gradient_size) * 90
            angular_hue_shift = np.degrees(angular_diff) * 0.3

            lamp_hue = (lamp_base_hue + distance_hue_shift + angular_hue_shift) % 360

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
        # chroma_contrast rescaled from 0.35 so peak chroma stays within 0.4
        oklch_output[:, 1] = np.clip(base_chroma + total_intensity * 0.185, 0.0, 0.4)

        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
