"""Raindrops appear on the surface, causing ripples outwards."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


class Raindrops(Pattern):
    """Raindrops with rainbow gradient halos."""

    name = "raindrops"
    description = "Raindrops with rainbow gradient halos"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Extract coordinates
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]

        # Raindrop parameters
        drops_per_second = 5.0
        ripple_lifetime = 4.0  # How long ripples last in seconds
        ripple_speed = 60.0  # How fast ripples expand (units/second)
        max_radius = 200.0  # Maximum distance ripples travel
        fade_in_time = 0.3  # Time for gentle fade-in at start
        ripple_width = 20.0  # Width of the ripple wave

        # Determine which raindrops are active (within ripple_lifetime of now)
        drop_interval = 1.0 / drops_per_second

        # Find the range of drop indices to consider
        latest_drop_idx = int(t / drop_interval)
        earliest_drop_idx = max(0, int((t - ripple_lifetime) / drop_interval))

        # Initialize accumulators
        total_intensity = np.zeros_like(x)
        weighted_hue = np.zeros_like(x)
        total_weight = np.zeros_like(x)

        # Process each active raindrop (bounded event window: <= 20 drops)
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
            rnd = seeded_random(f"raindrops-{drop_idx}", 2)
            drop_x = -150.0 + 300.0 * rnd[0]
            drop_y = -150.0 + 300.0 * rnd[1]

            # Calculate distance from each beam to this drop
            dist_to_drop = np.sqrt((x - drop_x) ** 2 + (y - drop_y) ** 2)

            # Current ripple radius (expands over time)
            current_ripple_radius = age * ripple_speed

            # Skip if ripples haven't reached this area yet or have passed
            ripple_distance = np.abs(dist_to_drop - current_ripple_radius)

            # Gentle fade-in at the beginning, then exponential decay
            if age < fade_in_time:
                # Smooth fade-in using a sine curve for gentleness
                age_falloff = np.sin((age / fade_in_time) * np.pi / 2)
            else:
                # After fade-in, apply exponential decay
                decay_age = age - fade_in_time
                age_falloff = np.exp(-decay_age * 1.2)

            distance_falloff = np.exp(-ripple_distance / ripple_width)

            # Only consider points close to the ripple
            mask = ripple_distance < ripple_width * 2

            intensity = np.zeros_like(dist_to_drop)
            intensity[mask] = distance_falloff[mask] * age_falloff

            # Create rainbow effect based on ripple position and age
            base_hue = (drop_idx * 137.5) % 360  # Golden-ratio spacing

            # Hue shifts based on distance from center and time
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

        # Clamp total intensity
        total_intensity = np.clip(total_intensity, 0, 1.5)

        # Set OKLCH values with base ambient lighting
        base_lightness = 0.03
        oklch_output[:, 0] = np.clip(base_lightness + total_intensity * 0.6, 0.0, 1.0)

        base_chroma = 0.01
        oklch_output[:, 1] = np.clip(base_chroma + total_intensity * 0.25, 0.0, 0.4)

        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
