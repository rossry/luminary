"""Aurora-like bands of light flow across the dome, shimmering and undulating."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class AuroraBands(Pattern):
    """Aurora-like bands of light flow across the dome with organic movement."""

    name = "aurora_bands"
    description = "Flowing aurora bands with organic shimmer across the dome surface."

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_beams = lights.shape[0]
        oklch_output = np.zeros((n_beams, 3))

        # Spherical coordinates. PHI_S is the inclination from +Z in radians
        # (0 at the north pole, pi at the south); the original pattern used an
        # elevation-in-degrees column, so convert. THETA_S is the azimuth.
        r = np.degrees(lights[:, LightColumns.PHI_S])  # elevation in degrees
        theta = lights[:, LightColumns.THETA_S]  # azimuth in radians

        # Aurora parameters
        band_speed = 0.3  # Gentle movement
        num_bands = 2  # Just two bands to keep it manageable

        # Color parameters
        base_lightness = 0.03
        max_intensity = 0.7
        base_chroma = 0.01
        max_chroma = 0.25  # rescaled so peak chroma stays within the 0.4 wire limit

        # Convert theta to degrees for easier math
        theta_deg = np.rad2deg(theta)  # -180 to 180

        # Avoid poles - aurora appears in bands around the sphere
        elevation_factor = np.sin(np.deg2rad(np.clip(r, 0.0, 180.0))) ** 0.8
        elevation_factor = np.clip(elevation_factor * 1.2, 0.0, 1.0)

        total_intensity = np.zeros(n_beams)

        # Create multiple aurora bands
        for band_idx in range(num_bands):
            # Each band moves at slightly different speed and position
            band_phase = band_idx * 180.0  # Bands on opposite sides
            band_center = ((t * band_speed * 40.0 + band_phase) % 360.0) - 180.0

            # Distance from band center
            angular_dist = np.abs(theta_deg - band_center)
            angular_dist = np.minimum(angular_dist, 360.0 - angular_dist)

            # Band width varies over time
            base_width = 25.0 + 10.0 * np.sin(t * 0.4 + band_idx)
            band_intensity = np.exp(-0.5 * (angular_dist / base_width) ** 2)

            # Add some undulation based on elevation
            undulation = 1.0 + 0.2 * np.sin(
                np.deg2rad(r) * 2.0 + t * 0.8 + band_idx * 2.0
            )
            band_intensity *= undulation

            total_intensity += band_intensity

        # Apply elevation masking
        total_intensity *= elevation_factor

        # Multi-layer shimmer effect
        shimmer1 = 0.8 + 0.2 * np.sin(t * 4.0 + theta * 1.5)
        shimmer2 = 0.9 + 0.1 * np.sin(t * 7.0 + np.deg2rad(r) * 3.0)
        total_intensity *= shimmer1 * shimmer2

        # Safe clipping
        total_intensity = np.clip(total_intensity, 0.0, 1.5)

        # Aurora color progression - green base with blue-purple variations
        base_hue = 140.0  # Aurora green

        # Subtle hue shifts
        hue_variation = 15.0 * np.sin(t * 0.3 + theta * 0.8)  # Slow color waves
        hue_variation += 8.0 * np.sin(np.deg2rad(r) * 1.5)  # Elevation-based shift

        final_hue = (base_hue + hue_variation) % 360.0

        # Intensity-based hue shifts (brighter areas get more blue/purple)
        intensity_hue_shift = np.where(
            total_intensity > 0.8, (total_intensity - 0.8) * 30.0, 0.0
        )
        final_hue = (final_hue + intensity_hue_shift) % 360.0

        # Set OKLCH values
        oklch_output[:, 0] = np.clip(
            base_lightness + total_intensity * max_intensity, 0.0, 1.0
        )
        oklch_output[:, 1] = np.clip(
            base_chroma + total_intensity * max_chroma, 0.0, 0.4
        )
        oklch_output[:, 2] = final_hue % 360.0

        return oklch_output
