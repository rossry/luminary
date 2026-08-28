"""Relay: bead races run on the physical wiring itself.

Every LED strip is a lane. Racers are beads of light that run the
strip in *index order* — which on the real build means they run the
serpentine: down the edge, in along the radial, out, around — so the
race traces the electrical path of the sculpture, the thing no
geometric pattern ever shows. Each round, every lane draws a seeded
finish time and a wobble (surging and flagging mid-race); the winner's
lane floods gold at the line, the field flickers out, everyone
breathes through a rest, and the next heat lines up with re-drawn
lane colors.

The race is pure schedule, not simulation: per (lane, round) the
finish time, wobble, and lane hue come from ``seeded_random``; a
bead's position is a closed form of race time whose wobble term is
zeroed at both ends, so it leaves exactly at the gun and finishes
exactly at its drawn time. Any frame at any ``t`` reconstructs the
same standings (spec §9.1.3).

Medium notes: this pattern reads best *close up* — it is about the
strips, not the sphere. Lanes hold one hue each (rotating assignments
every round), beads are ~10-LED pools with a short tail, and the only
full-field event is the winner's half-second flood.
"""

from __future__ import annotations

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.easing import env_ad, smootherstep
from luminary.patterns.primitives import Primitive
from luminary.patterns.util import seeded_random


class Relay(Primitive):
    name = "relay"
    description = "Bead races down the physical strip order, heat after heat"

    race_s = 14.0  # gun to the last plausible finish
    rest_s = 6.0  # lineup breath between heats
    bead_sigma = 0.030  # bead half-width, as a fraction of the strip
    tail = 0.10  # comet tail length, fraction of the strip
    wobble = 0.06  # mid-race surge amplitude, fraction of the strip
    lane_c = 0.105  # lane chroma
    base_l = 0.028
    salt = "relay"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        ctrl = lights[:, LightColumns.CONTROLLER].astype(np.int64)
        chan = lights[:, LightColumns.CHANNEL].astype(np.int64)
        idx = lights[:, LightColumns.INDEX]

        # Lanes = physical strips, in canonical (controller, channel) order.
        sids, inv = np.unique(ctrl * 64 + chan, return_inverse=True)
        k = len(sids)
        length = np.zeros(k)
        np.maximum.at(length, inv, idx)
        x = idx / np.maximum(length[inv], 1.0)  # 0..1 along each strip's wiring

        round_s = self.race_s + self.rest_s
        rnd = int(np.floor(t / round_s))
        tau = t - rnd * round_s

        # This heat's draw, per lane: finish time, wobble, lane colors.
        finish = self.race_s * (0.62 + 0.33 * seeded_random(f"{self.salt}-T-{rnd}", k))
        wob_f = 2.0 + 3.0 * seeded_random(f"{self.salt}-wf-{rnd}", k)
        wob_p = 2.0 * np.pi * seeded_random(f"{self.salt}-wp-{rnd}", k)
        hue_shift = 360.0 * seeded_random(f"{self.salt}-h-{rnd}", 1)[0]
        # Golden-angle spacing: neighboring lanes get far-apart hues.
        lane_hue = (np.arange(k) * 137.508 + hue_shift) % 360.0
        winner = int(np.argmin(finish))

        # Bead positions: exact at the gun and at each lane's finish.
        s = np.clip(tau / finish, 0.0, 1.0)
        gate = s * (1.0 - s)
        pos = (
            smootherstep(0.0, 1.0, s)
            + self.wobble * np.sin(wob_f * 2.0 * np.pi * s + wob_p) * gate
        )
        running = (tau >= 0.0) & (s < 1.0)

        # Per-light gather of this lane's state.
        pos_l = pos[inv]
        run_l = running[inv]
        hue_l = lane_hue[inv]
        d = x - pos_l
        sig = self.bead_sigma
        head = np.exp(-(d**2) / (2.0 * sig**2))
        behind = (d < 0.0) & (d > -3.5 * self.tail)
        comet = np.where(behind, 0.55 * np.exp(d / self.tail), 0.0)
        bead = np.where(run_l, np.maximum(head, comet), 0.0)

        # Finishes: the winner floods gold, the field acknowledges faintly.
        dt_fin = tau - finish
        flash = env_ad(dt_fin, 0.12, 0.9)
        lane_flash = np.where(np.arange(k) == winner, 0.60, 0.10) * flash
        flash_l = lane_flash[inv]

        # Rest breath: the whole field settles and swells once before the gun.
        rest = np.clip((tau - self.race_s) / self.rest_s, 0.0, 1.0)
        breathe = 0.020 * np.sin(np.pi * rest) if rest > 0.0 else 0.0

        out = np.empty((n, 3))
        out[:, 0] = np.clip(
            self.base_l + breathe + 0.60 * bead + 0.55 * flash_l, 0.0, 0.92
        )
        out[:, 1] = self.lane_c * np.clip(bead + flash_l, 0.12, 1.0) + 0.02
        # Lanes keep their hue; a winning flood turns the lane gold.
        gold = (flash_l > bead * 0.8) & (flash_l > 0.02)
        out[:, 2] = np.where(gold, 85.0, hue_l)
        return out
