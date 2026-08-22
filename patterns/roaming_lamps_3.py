"""Multiple lamps roaming around with rainbow gradient halos on the sphere."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class RoamingLamps3(Pattern):
    """Multiple lamps roaming around with rainbow gradient halos in spherical space."""

    name = "roaming_lamps_3"
    description = "Moving lamps with rainbow gradient halos in spherical polar space."

    @staticmethod
    def euclidean_distance(
        x1: np.ndarray,
        y1: np.ndarray,
        z1: np.ndarray,
        x2: float,
        y2: float,
        z2: float,
    ) -> np.ndarray:
        """Euclidean distance between two points in 3D space (vectorized)."""
        return np.sqrt(np.square(x2 - x1) + np.square(y2 - y1) + np.square(z2 - z1))

    @staticmethod
    def zin(t: float) -> float:
        """Linear triangle wave version of sin."""
        return 2 / np.pi * np.arcsin(np.sin(t))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Spherical coordinates. PHI_S is inclination from +Z in radians
        # (0 north pole, pi south); the original used elevation-in-degrees.
        r = np.degrees(lights[:, LightColumns.PHI_S])  # elevation in degrees
        theta = lights[:, LightColumns.THETA_S]  # azimuth in radians

        elevation_rad = np.deg2rad(r)
        sin_elev = np.sin(elevation_rad)
        beam_x = sin_elev * np.cos(theta)
        beam_y = sin_elev * np.sin(theta)
        beam_z = np.cos(elevation_rad)

        # lamp parameters
        num_lamps = 6
        move_speed = 0.7  # Radians per second for angular motion
        min_r = 10.0  # Minimum elevation
        max_r = 170.0  # Maximum elevation
        gradient_size = 0.4  # How far the gradient extends

        # Initialize intensity and hue arrays
        total_intensity = np.zeros_like(r)
        weighted_hue = np.zeros_like(r)
        total_weight = np.zeros_like(r)

        # Create roaming lamps in spherical space (bounded loop over 6 lamps)
        for lamp_idx in range(num_lamps):
            # Each lamp gets different motion parameters
            lamp_phase = lamp_idx * (2 * np.pi / num_lamps)

            # Radial motion (oscillating between min and max elevation)
            radial_freq = 0.4 + lamp_idx * 0.1
            lamp_r = min_r + (max_r - min_r) * (
                0.5 + 0.5 * self.zin(t * radial_freq + lamp_phase)
            )

            # Angular motion (rotating around, with some wobble)
            direction = 1 if lamp_idx % 2 == 0 else -1
            angular_freq = move_speed * (0.8 + lamp_idx * 0.3) * direction
            angular_wobble = 0.5 * self.zin(t * (radial_freq * 2) + lamp_phase * 1.7)
            lamp_theta = (t * angular_freq + lamp_phase + angular_wobble) % (2 * np.pi)
            lamp_elev = np.deg2rad(lamp_r)
            lamp_x = np.sin(lamp_elev) * np.cos(lamp_theta)
            lamp_y = np.sin(lamp_elev) * np.sin(lamp_theta)
            lamp_z = np.cos(lamp_elev)

            # Distance from each beam to this lamp on the unit sphere
            total_dist = self.euclidean_distance(
                beam_x, beam_y, beam_z, lamp_x, lamp_y, lamp_z
            )

            # Create intensity based on distance
            lamp_intensity = np.exp(-total_dist / gradient_size)

            # Each lamp gets a different base hue that shifts over time
            lamp_base_hue = (lamp_idx * 60 + t * 25) % 360

            # Hue shifts based on distance for rainbow effect
            distance_hue_shift = (total_dist / gradient_size) * 90

            lamp_hue = (lamp_base_hue + distance_hue_shift) % 360

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
