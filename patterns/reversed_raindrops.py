"""Raindrop ripples appear on the surface, contracting inwards and then vanishing."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


class ReversedRaindrops(Pattern):
    """Raindrop ripples appear on the surface, contracting inwards and vanishing."""

    name = "reversed_raindrops"
    description = "Raindrop ripples contract inwards and then vanish."

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Extract coordinates
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]

        # Raindrop parameters
        drops_per_second = 3.0
        ripple_lifetime = 1.0  # How long ripples last in seconds
        max_radius = 90.0  # Starting radius for contracting ripples
        ripple_speed = max_radius / ripple_lifetime
        fade_in_time = 0.4  # Time for gentle fade-in at start
        fade_out_time = 0.3  # Time for dramatic fade-out at "impact"

        # color parameters
        base_lightness = 0.03
        contrast = 0.6
        base_chroma = 0.01
        chroma_contrast = 0.21  # rescaled so peak chroma stays within the wire limit

        # Determine which raindrops are active (within ripple_lifetime of now)
        drop_interval = 1.0 / drops_per_second

        # Find the range of drop indices to consider
        latest_drop_idx = int(t / drop_interval)
        earliest_drop_idx = max(0, int((t - ripple_lifetime) / drop_interval))

        # Initialize accumulators
        total_intensity = np.zeros_like(x)
        weighted_hue = np.zeros_like(x)
        total_weight = np.zeros_like(x)

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

            # Deterministic position for this drop (pure function of drop_idx)
            rnd = seeded_random(f"reversed_raindrops-{drop_idx}", 2)
            drop_x = -150.0 + 300.0 * rnd[0]
            drop_y = -150.0 + 300.0 * rnd[1]

            # Calculate distance from each beam to this drop
            dist_to_drop = np.sqrt((x - drop_x) ** 2 + (y - drop_y) ** 2)

            # REVERSE: Current ripple radius (contracts over time)
            # Start at max_radius and shrink to 0
            current_ripple_radius = max_radius - (age * ripple_speed)

            # Skip if ripple has already contracted past this point
            if current_ripple_radius < 0:
                continue

            ripple_width = 20.0  # Width of the ripple wave
            ripple_distance = np.abs(dist_to_drop - current_ripple_radius)

            distance_falloff = np.exp(-ripple_distance / ripple_width)

            # Only consider points close to the ripple
            mask = ripple_distance < ripple_width * 2

            # Fade in and out of the ripple
            age_falloff = 1.0
            if age < fade_in_time:
                # Smooth fade-in using a sine curve for gentleness
                age_falloff *= np.sin((age / fade_in_time) * np.pi / 2)
            if age > ripple_lifetime - fade_out_time:
                # Smooth fade-out as we approach the impact
                time_to_impact = ripple_lifetime - age
                age_falloff *= np.sin((time_to_impact / fade_out_time) * np.pi / 2)

            intensity = np.zeros_like(dist_to_drop)
            intensity[mask] = distance_falloff[mask] * age_falloff

            # Create rainbow effect - hues shift as ripples contract
            base_hue = (drop_idx * 137.5) % 360  # Golden-ratio spacing

            # Hue shifts based on distance from center and time (reverse effect)
            distance_hue_shift = ((max_radius - dist_to_drop) / max_radius) * 180
            time_hue_shift = (ripple_lifetime - age) * 60  # Reverse time progression

            drop_hue = (base_hue + distance_hue_shift + time_hue_shift) % 360

            # Add this drop's contribution
            total_intensity += intensity
            weighted_hue += drop_hue * intensity
            total_weight += intensity

        # Avoid division by zero
        total_weight = np.maximum(total_weight, 1e-6)

        # Calculate final hue (weighted average)
        final_hue = weighted_hue / total_weight

        # Clamp total intensity
        total_intensity = np.clip(total_intensity, 0, 1.8)

        # Set OKLCH values with base ambient lighting
        oklch_output[:, 0] = np.clip(
            base_lightness + total_intensity * contrast, 0.0, 1.0
        )
        oklch_output[:, 1] = np.clip(
            base_chroma + total_intensity * chroma_contrast, 0.0, 0.4
        )
        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
