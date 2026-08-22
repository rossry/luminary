"""Raindrop ripples appear on the surface, contracting inwards and then vanishing.

Respects the spherical dome.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


class ReversedRaindropsSpherical(Pattern):
    """Raindrop ripples contract inwards across the spherical dome, then vanish."""

    name = "reversed_raindrops_spherical"
    description = "Raindrop ripples contract inwards and then vanish."

    @staticmethod
    def euclidean_distance(
        r1: np.ndarray, theta1: np.ndarray, r2: float, theta2: float
    ) -> np.ndarray:
        """Chord distance between points on the unit sphere.

        Args:
            r1, r2: elevation angles in degrees (0 = north pole, 180 = south).
            theta1, theta2: azimuth angles in radians.
        """
        sin_r1 = np.sin(np.deg2rad(r1))
        x1 = sin_r1 * np.cos(theta1)
        y1 = sin_r1 * np.sin(theta1)
        z1 = np.cos(np.deg2rad(r1))

        sin_r2 = np.sin(np.deg2rad(r2))
        x2 = sin_r2 * np.cos(theta2)
        y2 = sin_r2 * np.sin(theta2)
        z2 = np.cos(np.deg2rad(r2))
        return np.sqrt(np.square(x2 - x1) + np.square(y2 - y1) + np.square(z2 - z1))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Spherical coordinates. PHI_S is inclination from +Z in radians
        # (0 north pole, pi south); the original used elevation-in-degrees.
        r = np.degrees(lights[:, LightColumns.PHI_S])  # elevation in degrees
        theta = lights[:, LightColumns.THETA_S]  # azimuth in radians

        # Raindrop parameters
        drops_per_second = 2.5
        ripple_lifetime = 1.5  # How long ripples last in seconds
        max_radius = 45.0  # Starting radius for contracting ripples (in degrees)
        ripple_speed = max_radius / ripple_lifetime
        fade_in_time = 0.4  # Time for gentle fade-in at start
        fade_out_time = 0.4  # Time for dramatic fade-out at "impact"
        ripple_width = 15.0  # Width of the ripple wave (in degrees)

        # color parameters
        base_lightness = 0.03
        contrast = 0.6
        base_chroma = 0.01
        chroma_contrast = 0.19  # rescaled so peak chroma stays within the wire limit

        # Determine which raindrops are active
        drop_interval = 1.0 / drops_per_second

        # Find the range of drop indices to consider
        latest_drop_idx = int(t / drop_interval)
        earliest_drop_idx = max(0, int((t - ripple_lifetime) / drop_interval))

        # Initialize accumulators
        total_intensity = np.zeros_like(r)
        weighted_hue = np.zeros_like(r)
        total_weight = np.zeros_like(r)

        # Process each active raindrop (bounded event window)
        for drop_idx in range(earliest_drop_idx, latest_drop_idx + 1):
            drop_time = drop_idx * drop_interval

            # Skip future drops
            if drop_time > t:
                continue

            # Time since this drop occurred
            age = t - drop_time

            # Skip drops that are too old
            if age > ripple_lifetime:
                continue

            # Deterministic position on the sphere (pure function of drop_idx).
            rnd = seeded_random(f"reversed_raindrops_spherical-{drop_idx}", 2)
            drop_r = np.rad2deg(np.arccos(-0.9 + 1.8 * rnd[0]))  # elevation, deg
            drop_theta = -np.pi + 2.0 * np.pi * rnd[1]  # azimuth, rad

            # Chord distance from each beam to the drop, scaled to degrees.
            dist_to_drop = self.euclidean_distance(r, theta, drop_r, drop_theta) * (
                180 / np.pi
            )

            # REVERSE: Current ripple radius (contracts over time)
            current_ripple_radius = max_radius - (age * ripple_speed)

            # Skip if ripple has already contracted past this point
            if current_ripple_radius < 0:
                continue

            ripple_distance = np.abs(dist_to_drop - current_ripple_radius)

            # Distance threshold for ripple visibility
            distance_threshold = ripple_width * 3.0

            # Distance falloff - gaussian-like profile
            distance_falloff = np.exp(-ripple_distance / ripple_width)

            # Fade in and out of the ripple
            age_falloff = 1.0
            if age < fade_in_time:
                age_falloff *= age / fade_in_time
            if age > ripple_lifetime - fade_out_time:
                time_to_impact = ripple_lifetime - age
                age_falloff *= time_to_impact / fade_out_time

            # Apply effects to all points within threshold
            mask = ripple_distance < distance_threshold

            intensity = np.zeros_like(dist_to_drop)
            intensity[mask] = distance_falloff[mask] * age_falloff

            # Create rainbow effect
            base_hue = (drop_idx * 137.5) % 360

            # Hue shifts based on angular distance and time
            distance_hue_shift = (dist_to_drop / max_radius) * 180
            time_hue_shift = age * 60

            drop_hue = (base_hue + distance_hue_shift + time_hue_shift) % 360

            # Add this drop's contribution
            total_intensity += intensity
            weighted_hue += drop_hue * intensity
            total_weight += intensity

        # Avoid division by zero
        total_weight = np.maximum(total_weight, 1e-6)

        # Calculate final hue (weighted average)
        final_hue = weighted_hue / total_weight

        # Clip intensity
        total_intensity = np.clip(total_intensity, 0, 2.0)

        # Set OKLCH values
        oklch_output[:, 0] = np.clip(
            base_lightness + total_intensity * contrast, 0.0, 1.0
        )
        oklch_output[:, 1] = np.clip(
            base_chroma + total_intensity * chroma_contrast, 0.0, 0.4
        )
        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
