"""Magical fireflies twinkling and drifting across the dome surface."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns

class Fireflies(LuminaryPattern):
    """Magical fireflies twinkling and drifting across the dome surface."""

    @property
    def name(self) -> str:
        return "Fireflies"

    @property
    def description(self) -> str:
        return "Hundreds of magical fireflies twinkling and slowly drifting across the dome."

    def __init__(self):
        super().__init__()
        # We'll cache firefly positions and states to maintain consistency
        self._last_update = -1.0
        self._fireflies = []
        self._num_fireflies = 150
        self._initialized = False

    def euclidean_distance(self, r1, theta1, r2, theta2):
        """Calculate Euclidean distance between points on sphere."""
        sin_r1 = np.sin(np.deg2rad(r1))
        x1 = sin_r1 * np.cos(theta1)
        y1 = sin_r1 * np.sin(theta1)
        z1 = np.cos(np.deg2rad(r1))

        sin_r2 = np.sin(np.deg2rad(r2))
        x2 = sin_r2 * np.cos(theta2)
        y2 = sin_r2 * np.sin(theta2)
        z2 = np.cos(np.deg2rad(r2))

        return np.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2) * (180/np.pi)

    def initialize_fireflies(self):
        """Initialize firefly positions and properties."""
        self._fireflies = []

        for i in range(self._num_fireflies):
            # Random initial position on sphere (avoiding poles)
            r = np.rad2deg(np.arccos(np.random.uniform(-0.9, 0.9)))
            theta = np.random.uniform(-np.pi, np.pi)

            firefly = {
                'id': i,
                'r': r,
                'theta': theta,
                'base_r': r,  # Original position for drift reference
                'base_theta': theta,
                'brightness_phase': np.random.uniform(0, 2*np.pi),  # For twinkling
                'brightness_speed': np.random.uniform(0.8, 2.5),    # How fast it twinkles
                'max_brightness': np.random.uniform(0.6, 1.0),      # Peak brightness
                'drift_speed': np.random.uniform(0.05, 0.15),       # How fast it drifts
                'drift_radius': np.random.uniform(8, 25),           # How far it drifts from base
                'hue': np.random.uniform(45, 65),                   # Warm firefly colors (yellow-green)
                'size': np.random.uniform(4, 12),                   # Glow radius
                'active_probability': 0.85,                         # Chance of being active at any time
                'last_active_check': 0
            }
            self._fireflies.append(firefly)

        self._initialized = True

    def update_firefly_positions(self, t):
        """Update firefly positions and states."""
        for firefly in self._fireflies:
            # Drift motion - slow circular drift around base position
            drift_angle = t * firefly['drift_speed']
            drift_offset_r = firefly['drift_radius'] * np.sin(drift_angle) * 0.5
            drift_offset_theta = (firefly['drift_radius'] / 180) * np.cos(drift_angle) * 0.8

            # Update position with drift
            firefly['r'] = firefly['base_r'] + drift_offset_r
            firefly['theta'] = firefly['base_theta'] + drift_offset_theta

            # Keep in bounds
            firefly['r'] = np.clip(firefly['r'], 5, 175)
            if firefly['theta'] > np.pi:
                firefly['theta'] -= 2*np.pi
            elif firefly['theta'] < -np.pi:
                firefly['theta'] += 2*np.pi

            # Randomly toggle active state occasionally
            if t - firefly['last_active_check'] > np.random.exponential(2.0):
                firefly['active'] = np.random.random() < firefly['active_probability']
                firefly['last_active_check'] = t

    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Render magical fireflies."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)

        # Initialize fireflies if needed
        if not self._initialized:
            np.random.seed(42)  # Consistent firefly placement
            self.initialize_fireflies()
            np.random.seed()  # Reset to random

        # Update firefly positions
        if abs(t - self._last_update) > 0.05:  # Update at most 20fps
            self.update_firefly_positions(t)
            self._last_update = t

        # Extract coordinates
        r = beam_array[:, BeamArrayColumns.R]
        theta = beam_array[:, BeamArrayColumns.THETA]

        # Base ambient lighting (very dim forest floor)
        base_lightness = 0.02
        base_chroma = 0.05
        base_hue = 120  # Forest green

        # Initialize with ambient lighting
        oklch_output[:, 0] = base_lightness
        oklch_output[:, 1] = base_chroma
        oklch_output[:, 2] = base_hue

        # Accumulate firefly contributions
        total_brightness = np.zeros(n_beams)
        weighted_hue = np.zeros(n_beams)
        weighted_chroma = np.zeros(n_beams)
        total_weight = np.zeros(n_beams)

        for firefly in self._fireflies:
            # Skip if firefly is not active
            if not firefly.get('active', True):
                continue

            # Calculate brightness (twinkling)
            brightness_phase = firefly['brightness_phase'] + t * firefly['brightness_speed']
            brightness_envelope = (np.sin(brightness_phase) + 1) / 2  # 0 to 1

            # Add some randomness to the twinkling
            random_flicker = 0.8 + 0.4 * np.sin(brightness_phase * 3.7 + firefly['id'])
            brightness = firefly['max_brightness'] * brightness_envelope * random_flicker

            # Skip very dim fireflies
            if brightness < 0.1:
                continue

            # Distance from each LED to this firefly
            distances = self.euclidean_distance(r, theta, firefly['r'], firefly['theta'])

            # Firefly glow falloff (soft Gaussian-like)
            glow_size = firefly['size']
            influence = np.exp(-(distances / glow_size)**2)

            # Only affect nearby LEDs
            mask = distances < glow_size * 2.5
            if not np.any(mask):
                continue

            # Calculate this firefly's contribution
            contribution = brightness * influence

            # Firefly colors - warm yellow-green with some variation
            hue_variation = 15 * np.sin(t * 0.3 + firefly['id'])
            firefly_hue = firefly['hue'] + hue_variation
            firefly_chroma = 0.15 + 0.1 * brightness

            # Accumulate weighted values
            total_brightness[mask] += contribution[mask]
            weighted_hue[mask] += firefly_hue * contribution[mask]
            weighted_chroma[mask] += firefly_chroma * contribution[mask]
            total_weight[mask] += contribution[mask]

        # Avoid division by zero
        total_weight = np.maximum(total_weight, 1e-6)

        # Compute final colors
        final_hue = np.where(total_weight > 1e-6, weighted_hue / total_weight, base_hue)
        final_chroma = np.where(total_weight > 1e-6, weighted_chroma / total_weight, base_chroma)

        # Combine with base lighting
        final_lightness = np.clip(base_lightness + total_brightness * 0.7, 0, 1)
        final_chroma = np.clip(base_chroma + final_chroma, 0, 0.3)

        # Set final OKLCH values
        oklch_output[:, 0] = final_lightness
        oklch_output[:, 1] = final_chroma
        oklch_output[:, 2] = final_hue

        return oklch_output