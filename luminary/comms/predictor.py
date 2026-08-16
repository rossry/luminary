"""The shared dead-reckoning predictor (spec §11.5).

One implementation of the frame-step state machine, used by BOTH the encoder
(to simulate the decoder, spec §11.5.3) and the reference decoder — so the two
cannot diverge by construction. All arithmetic is int32 with arithmetic
(floor) shifts, exactly as normative in spec §11.5.4; the JS and C++ decoders
mirror these operations bit-for-bit.

State per ACTIVE light: q (n,3) quantized OKLCH, v (n,3) velocity in 1/8-LSB
fixed point.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from luminary.comms import protocol as p


def new_state(n_active: int) -> Tuple[np.ndarray, np.ndarray]:
    """Fresh (q, v) state: all zeros (black, at rest)."""
    return (
        np.zeros((n_active, 3), dtype=np.int32),
        np.zeros((n_active, 3), dtype=np.int32),
    )


def hue_wrap_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest signed hue difference a-b in [-128, 127] (mod 256)."""
    out: np.ndarray = ((a - b + 128) % p.QH_MOD) - 128
    return out


def predict(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Per-component prediction: q + round(v / 8), clamped/wrapped (spec §11.5.4)."""
    pred = q + ((v + p.V_ROUND) >> p.V_SHIFT)
    out: np.ndarray = np.empty_like(pred)
    out[:, 0] = np.clip(pred[:, 0], 0, p.QL_LEVELS - 1)
    out[:, 1] = np.clip(pred[:, 1], 0, p.QC_LEVELS - 1)
    out[:, 2] = pred[:, 2] % p.QH_MOD
    return out


def apply_delta(
    q: np.ndarray,
    v: np.ndarray,
    positions: Optional[np.ndarray],
    corrections: Optional[np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """One DELTA frame step: every light coasts on its prediction; corrected
    lights add their correction; velocities blend toward the realized step.

    Returns new (q, v); inputs are not mutated.
    """
    pred = predict(q, v)
    q_new = pred.copy()
    if positions is not None and positions.size:
        assert corrections is not None
        q_new[positions, 0] = np.clip(
            pred[positions, 0] + corrections[:, 0], 0, p.QL_LEVELS - 1
        )
        q_new[positions, 1] = np.clip(
            pred[positions, 1] + corrections[:, 1], 0, p.QC_LEVELS - 1
        )
        q_new[positions, 2] = (pred[positions, 2] + corrections[:, 2]) % p.QH_MOD

    d = np.empty_like(q_new)
    d[:, 0:2] = q_new[:, 0:2] - q[:, 0:2]
    d[:, 2] = hue_wrap_diff(q_new[:, 2], q[:, 2])
    v_new = v + (((d << p.V_SHIFT) - v) >> p.ALPHA_SHIFT)
    return q_new, v_new


def apply_keyframe(q_key: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """KEYFRAME step: state snaps to the keyframe values, velocity resets."""
    return q_key.astype(np.int32).copy(), np.zeros_like(q_key, dtype=np.int32)


def error_to_target(
    q: np.ndarray, v: np.ndarray, target: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Encoder-side: (prediction, raw error, saturated correction) vs target.

    The raw error ranks lights (spec §11.6.2); the saturated correction is
    what a DELTA op can actually transmit (spec §11.4.3).
    """
    pred = predict(q, v)
    err = np.empty_like(pred)
    err[:, 0:2] = target[:, 0:2] - pred[:, 0:2]
    err[:, 2] = hue_wrap_diff(target[:, 2], pred[:, 2])

    corr = np.empty_like(err)
    corr[:, 0] = np.clip(err[:, 0], -p.DELTA_MAX[0], p.DELTA_MAX[0])
    corr[:, 1] = np.clip(err[:, 1], -p.DELTA_MAX[1], p.DELTA_MAX[1])
    corr[:, 2] = np.clip(err[:, 2], -p.DELTA_MAX[2], p.DELTA_MAX[2])
    return pred, err, corr
