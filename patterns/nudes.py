"""Fire-like organic flowing pattern."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class FireLikePattern(LuminaryPattern):
    """Fire-like pattern made from overlapping ellipses + arcs."""

    def __init__(self):
        # Randomize colors each time the pattern starts
        import random
        self.rng = random.Random(random.randint(0, 1000000))
        
        # Generate highly saturated random base hue
        self.base_hue = self.rng.uniform(0, 360)
        
        # Create complementary color palette (base + variations)
        self.hue_range = 60  # Degrees of hue variation around base
        
    @property
    def name(self) -> str:
        return "Fire-like Pattern"

    @property
    def description(self) -> str:
        return "Organic flowing shapes with warm colors suggesting fire and flame movement."

    # -------- SDF helpers (vectorized) --------
    @staticmethod
    def _rotate(x, y, ang):
        ca = np.cos(ang); sa = np.sin(ang)
        return x * ca - y * sa, x * sa + y * ca

    @staticmethod
    def _sd_ellipse(x, y, cx, cy, rx, ry, ang=0.0):
        # Signed distance ~0 on ellipse; negative inside. Normalized to rx/ry.
        xp = x - cx
        yp = y - cy
        # rotate point by -ang (equivalently rotate ellipse by +ang)
        ca = np.cos(ang); sa = np.sin(ang)
        xr =  ca * xp + sa * yp
        yr = -sa * xp + ca * yp
        q = np.sqrt((xr / (rx + 1e-6))**2 + (yr / (ry + 1e-6))**2) - 1.0
        return q  # unitless; 0 on rim

    @staticmethod
    def _sd_circle(x, y, cx, cy, r):
        return np.sqrt((x - cx)**2 + (y - cy)**2) - r

    @staticmethod
    def _contour_from_sd(sd, width):
        # Bright line near sd==0; decays quickly. width ~ line softness.
        return np.exp(-np.abs(sd) / (width + 1e-6))

    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """
        Generates softly shaded, warm-toned contour lines hinting at classical figure sketches.
        No explicit anatomical detail; reads as 'nudes' from a distance.
        """
        n = beam_array.shape[0]
        out = np.zeros((n, 3), dtype=np.float32)

        # ---------- Coordinates (normalize to roughly [-1,1]) ----------
        x_raw = beam_array[:, BeamArrayColumns.X]
        y_raw = beam_array[:, BeamArrayColumns.Y]

        # Robust centering & scaling across arbitrary geometries
        x_min, x_max = np.min(x_raw), np.max(x_raw)
        y_min, y_max = np.min(y_raw), np.max(y_raw)
        cx = 0.5 * (x_min + x_max)
        cy = 0.5 * (y_min + y_max)
        sx = max(1e-6, 0.5 * (x_max - x_min))
        sy = max(1e-6, 0.5 * (y_max - y_min))
        x = (x_raw - cx) / sx
        y = (y_raw - cy) / sy

        # Slight overall drift/tilt over time (keeps it organic)
        drift = 0.12 * np.sin(t * 0.15)
        x, y = self._rotate(x, y, drift)

        # ---------- Temporal envelopes ----------
        # slow 'breath' for line width & lightness
        breath = 0.5 * (1.0 + np.sin(t * 2 * np.pi * 0.18))
        breath = 3 * breath**2 - 2 * breath**3  # ease-in-out
        line_w = 0.045 * (0.85 + 0.35 * breath)  # line softness
        hue_drift = 6.0 * np.sin(t * 0.12)
        warm_pulse = 0.06 * np.sin(t * 0.08)

        # ---------- Movement patterns for figure parts ----------
        # Each part moves with different speed and phase for organic motion (3x faster)
        slow_drift = t * 1.2
        med_drift = t * 2.1
        fast_drift = t * 3.3
        
        # Individual movement offsets for each body part
        torso_dx = 0.08 * np.sin(slow_drift * 0.6)
        torso_dy = 0.06 * np.cos(slow_drift * 0.8)
        
        hip_dx = 0.12 * np.sin(med_drift * 0.5 + 1.0)
        hip_dy = 0.10 * np.cos(med_drift * 0.7 + 0.5)
        
        shoulder_dx = 0.15 * np.sin(fast_drift * 0.4 + 2.1)
        shoulder_dy = 0.08 * np.cos(fast_drift * 0.9 + 1.3)
        
        thigh_dx = 0.10 * np.sin(slow_drift * 0.9 + 3.8)
        thigh_dy = 0.14 * np.cos(slow_drift * 0.3 + 2.7)
        
        backarc_dx = 0.05 * np.sin(med_drift * 0.2 + 4.2)
        backarc_dy = 0.07 * np.cos(med_drift * 0.6 + 1.8)

        # ---------- "Figure" primitives with movement ----------
        # Base positions with movement offsets applied
        sd_torso   = self._sd_ellipse(x, y,  0.00 + torso_dx,  0.05 + torso_dy, 0.55, 0.85,  0.08)
        sd_hip     = self._sd_ellipse(x, y,  0.18 + hip_dx, -0.35 + hip_dy, 0.62, 0.42, -0.22)
        sd_shoulder= self._sd_ellipse(x, y, -0.35 + shoulder_dx,  0.35 + shoulder_dy, 0.36, 0.26,  0.30)
        sd_thigh   = self._sd_ellipse(x, y,  0.35 + thigh_dx, -0.65 + thigh_dy, 0.70, 0.36, -0.35)
        sd_backarc = self._sd_circle (x, y, -1.10 + backarc_dx,  0.15 + backarc_dy, 1.40)

        # Contour intensity from rims (sum of soft lines)
        line_int = (
            self._contour_from_sd(sd_torso, line_w) +
            self._contour_from_sd(sd_hip, line_w) +
            self._contour_from_sd(sd_shoulder, line_w) +
            self._contour_from_sd(sd_thigh, line_w*1.15) +
            self._contour_from_sd(sd_backarc, line_w*1.2)
        )

        # Soft interior shading (negative = inside shape); clamp to [0,1]
        fill_torso = np.clip(1.0 - np.maximum(0.0, sd_torso + 0.25) / 0.8, 0.0, 1.0)
        fill_hip   = np.clip(1.0 - np.maximum(0.0, sd_hip   + 0.20) / 0.7, 0.0, 1.0)
        fill_mix   = np.clip(0.55*fill_torso + 0.45*fill_hip, 0.0, 1.0)

        # Mild pseudo-noise so it feels sketchy (no external deps)
        noise = np.sin(11.3 * x + 5.7 * y + 0.4 * t) * np.sin(7.1 * x - 9.2 * y - 0.33 * t)
        noise = 0.06 * noise

        # ---------- OKLCH synthesis ----------
        # Lightness: warm paper base + contour highlight + interior wash
        L_base = 0.16 + 0.03 * (y + 1.0)  # slight vertical gradient
        L = L_base + 0.58 * np.clip(line_int, 0, 1) + 0.26 * fill_mix + 0.05 * breath + noise
        L = np.clip(L, 0.05, 0.92)

        # Chroma: highly saturated for vibrant colors
        C = 0.25 + 0.20 * fill_mix + 0.15 * np.clip(line_int, 0, 1) + warm_pulse + 0.03 * noise
        C = np.clip(C, 0.15, 0.45)  # Much higher saturation

        # Hue: randomized base color with variations
        # OKLCH hue in degrees - using randomized base
        h = (self.base_hue + 
             self.rng.uniform(-self.hue_range/2, self.hue_range/2) +  # Random variation around base
             hue_drift + 
             4.0 * x + 2.0 * y + 
             9.0 * np.clip(line_int, 0, 1)) % 360.0

        out[:, 0] = L.astype(np.float32)
        out[:, 1] = C.astype(np.float32)
        out[:, 2] = h.astype(np.float32)
        return out
