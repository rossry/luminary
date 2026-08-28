"""Spiegel: for Arvo Pärt's *Spiegel im Spiegel*.

Timed to the Minkler–Johnson recording (viola and piano, 11:55) —
name the file ``spiegel-im-spiegel.mp3`` in ``var/audio`` and the
stage pairs them.

Mirror in mirror: the whole render is symmetric across the sphere's
own mirror plane (azimuth negated, the geometry's x = 0 symmetry from
the craft notes). Every element either lives ON that plane or is
azimuth-independent, so each light and its reflection see the same
thing — held by ``test_spiegel_is_mirror_symmetric``.

**The expansion.** The viola does not repeat. Pärt's melodic voice
leaves the tonic, reaches one step further than last time, and comes
home; the next phrase goes the other way, one step further again.
Nothing else happens for twelve minutes, and it is one of the most
affecting things in music. So the line here is a single band that
leaves the sphere's middle, reaches its turn, and returns — up, then
down, then higher, then lower, thirty times, each phrase widening and
lasting a little longer than the one before, until the last ones sweep
nearly apex to rim and take half a minute to do it. The reach IS the
arc: the dynamics never change, because Pärt's don't.

The piano does not develop at all. Three soft bells climb the mirror
meridian itself, low-middle-high like the rising triad, rocking
forever, exactly as they did in the first bar. That is the whole
relationship — one voice expanding, one voice refusing to.
"""

import numpy as np

from luminary.patterns.easing import env_ad
from luminary.patterns.primitives import Primitive
from luminary.patterns.util import phi_theta


def _phrase_edges(count: int, base_s: float, grow: float) -> np.ndarray:
    """Start time of every phrase, plus the end of the last (count+1,).

    Phrase ``p`` lasts ``base_s * (1 + grow * p/(count-1))`` — the
    reach widens and the breath lengthens with it. A precomputed
    boundary array is a pure function of its three arguments, so
    ``searchsorted`` on it stays inside the stateless contract.
    """
    u = np.arange(count, dtype=np.float64) / max(count - 1, 1)
    return np.concatenate([[0.0], np.cumsum(base_s * (1.0 + grow * u))])


class Spiegel(Primitive):
    name = "spiegel"
    description = "Mirror in mirror: a widening line and three bells (11:55)"
    audio = "spiegel-im-spiegel.mp3"
    duration = 715.0  # the Minkler–Johnson recording
    notes = (
        "A band of pale light leaves the middle of the sphere, reaches its "
        "turn, and comes home; the next phrase goes the other way and one "
        "step further. Thirty times, each wider and slower than the last, "
        "until the final phrases sweep nearly the whole sphere and take "
        "half a minute to do it — while three soft bells climb the mirror "
        "line underneath, low, middle, high, exactly as they did in the "
        "first bar. One voice expanding, one voice refusing to; everything "
        "answered by its own reflection. The stillest music there is — let "
        "the room get quiet enough to hear the lights."
    )

    # The expansion. Thirty phrases over the recording: the first is a
    # short lean either side of the middle, the last a slow sweep from
    # nearly the apex to nearly the rim.
    # 30 x 18.33 x (1 + 0.6/2) = 714.9 s: the phrases fill the recording
    # and the last one lands on the final chord.
    phrases = 30
    phrase_s = 18.33  # the first phrase's out-and-back
    phrase_grow = 0.6  # the last one lasts this much longer again
    reach_from = 0.10  # turning point, fraction of the phi span from center
    reach_to = 0.46  # ...by the final phrase: very nearly the whole sphere
    turn_glow = 0.35  # the reached note is the expressive one
    line_l = 0.45
    line_sigma_deg = 5.0

    # The piano: unchanged, forever.
    bar_s = 6.0  # the rocking cycle: three bells per bar
    bell_l = 0.30
    bell_sigma_deg = 6.5

    floor_l = 0.022
    hue = 86.0  # F-major white-gold
    chroma = 0.04

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        phi, th = phi_theta(lights)
        span = float(np.max(phi)) or 1.0

        # --- the viola: out from the tonic, and home ----------------------
        edges = _phrase_edges(self.phrases, self.phrase_s, self.phrase_grow)
        # Past the last phrase the piece has said what it had to say; it
        # keeps breathing on the final width rather than snapping back.
        p = int(np.searchsorted(edges, t, side="right")) - 1
        p = min(max(p, 0), self.phrases - 1)
        u = (t - edges[p]) / (edges[p + 1] - edges[p])
        u = min(max(u, 0.0), 1.0)

        widen = p / max(self.phrases - 1, 1)
        reach = self.reach_from + (self.reach_to - self.reach_from) * widen
        # Out and back on a half-sine: the line rests at the tonic between
        # phrases, so the middle of the sphere is where it always returns.
        travel = np.sin(np.pi * u)
        center = 0.5 * span
        offset = reach * span * travel * (1.0 if p % 2 == 0 else -1.0)
        sigma = np.radians(self.line_sigma_deg)
        # Azimuth-independent, so the mirror is exact by construction.
        line = np.exp(-((phi - (center + offset)) ** 2) / (2.0 * sigma**2))
        line = line * self.line_l * (1.0 + self.turn_glow * travel * travel)

        # --- the piano: three bells ON the mirror meridian itself ---------
        # (azimuths 0° and 180° — every light's reflection sees exactly
        # what it sees), placed low, middle, high like the rising triad,
        # one ringing per third of the bar, forever.
        sin_phi = np.sin(phi)
        nl = np.column_stack([sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)])
        bsig = np.radians(self.bell_sigma_deg)
        t_in = t % self.bar_s
        bells = np.zeros(n)
        for i, (az_deg, phi_frac) in enumerate(
            ((0.0, 0.85), (180.0, 0.62), (0.0, 0.38))
        ):
            az = np.radians(az_deg)
            bell_phi = phi_frac * span
            axis = np.array(
                [
                    np.sin(bell_phi) * np.cos(az),
                    np.sin(bell_phi) * np.sin(az),
                    np.cos(bell_phi),
                ]
            )
            pool = np.exp((nl @ axis - 1.0) / (bsig**2))
            dt = t_in - i * (self.bar_s / 3.0)
            if dt < 0.0:
                dt += self.bar_s
            bells = np.maximum(bells, pool * float(env_ad(dt, 0.15, 1.1)) * self.bell_l)

        level = np.maximum(line, bells)
        out = np.empty((n, 3))
        out[:, 0] = self.floor_l + level
        out[:, 1] = self.chroma * np.clip(level / self.line_l, 0.0, 1.0) + 0.012
        out[:, 2] = self.hue
        return out
