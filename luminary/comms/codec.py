"""Encoder and reference Decoder for the Luminary wire protocol (spec §11.8).

The Encoder holds, per controller, its exact model of the decoder state — the
same (q, v) arrays maintained by the same :mod:`predictor` functions the
Decoder uses — and chooses error-ranked, budgeted corrections (spec §11.6).
The Decoder here is the normative reference implementation: it initializes
from SESSION bytes alone and is the oracle for the JS/C++ ports via golden
vectors (spec §11.9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from luminary.comms import predictor
from luminary.comms import protocol as p
from luminary.geometry.lights import Kind, LightsGeometry


@dataclass
class CodecConfig:
    """Tunables (spec §11.8.2); wire-format constants live in protocol.py.

    ``budget_bytes`` caps DELTA frames (per controller, per frame). KEYFRAMEs
    are exempt — they are 2 bytes/light regardless and their cost is amortized
    by ``keyframe_interval``; link budgeting (e.g. §12.2's baud math) leaves
    utilization headroom for them.
    """

    keyframe_interval: int = 60  # frames between keyframes (~2s at 30fps)
    budget_bytes: Optional[int] = None  # DELTA cap per controller per frame
    brightness: int = 255
    color_correction: Tuple[int, int, int] = (255, 255, 255)


@dataclass
class _ControllerState:
    controller: int
    active_rows: np.ndarray  # rows into the lights array, canonical order
    q: np.ndarray
    v: np.ndarray
    frames_since_keyframe: int = 0
    need_keyframe: bool = True


@dataclass
class EncoderStats:
    """Running statistics for the operator UI / budget tuning (spec §14.6)."""

    frames: int = 0
    keyframes: int = 0
    bytes_sent: int = 0
    ops_sent: int = 0
    lights: int = 0

    def bytes_per_light_frame(self) -> float:
        if not self.frames or not self.lights:
            return 0.0
        return self.bytes_sent / (self.frames * self.lights)


class Encoder:
    """Encodes OKLCH frames into wire bytes for every controller (spec §11.8.1)."""

    def __init__(self, lights: LightsGeometry, config: Optional[CodecConfig] = None):
        self.lights = lights
        self.config = config or CodecConfig()
        self.states: Dict[int, _ControllerState] = {}
        total_active = 0
        for controller in lights.controllers:
            active_rows = lights.active_rows_for_controller(controller)
            q, v = predictor.new_state(active_rows.size)
            self.states[controller] = _ControllerState(
                controller=controller, active_rows=active_rows, q=q, v=v
            )
            total_active += int(active_rows.size)
        self.stats = EncoderStats(lights=total_active)

    # ------------------------------------------------------------------ session

    def session_frames(self, t: float = 0.0) -> List[bytes]:
        """One SESSION frame per controller (spec §11.7.2)."""
        frames = []
        for controller in sorted(self.states):
            payload = p.build_session_payload(
                self.lights.channel_strips(controller),
                self.config.brightness,
                self.config.color_correction,
            )
            frames.append(p.build_frame(p.FRAME_SESSION, controller, t, payload))
        return frames

    def force_keyframe(self) -> None:
        """Next encode() emits keyframes (session start, swap, resync; spec §11.7.3)."""
        for state in self.states.values():
            state.need_keyframe = True

    # ------------------------------------------------------------------- encode

    def encode(self, oklch: np.ndarray, t: float) -> List[bytes]:
        """Encode one frame of pattern output (all rows) into wire frames."""
        if oklch.shape[0] != self.lights.n:
            raise ValueError(
                f"oklch has {oklch.shape[0]} rows, lights geometry has {self.lights.n}"
            )
        frames = []
        for controller in sorted(self.states):
            state = self.states[controller]
            target = p.quantize(oklch[state.active_rows])
            due = (
                state.need_keyframe
                or state.frames_since_keyframe >= self.config.keyframe_interval
            )
            if due:
                keyframe = self._encode_keyframe(state, target, t)
                self.stats.keyframes += 1
                self.stats.bytes_sent += len(keyframe)
                frames.append(keyframe)
                # Same-tick heal (spec §11.7.3a): the ranked delta pass now
                # runs against the just-snapped model, so keyframe rounding
                # residue and the velocity reset never outlive this tick —
                # without it, every cadence keyframe pulses slow dark content
                # (half the lights dip one LSB for several frames).
            frame = self._encode_delta(state, target, t)
            state.frames_since_keyframe = 0 if due else state.frames_since_keyframe + 1
            self.stats.bytes_sent += len(frame)
            frames.append(frame)
        self.stats.frames += 1
        return frames

    def _encode_keyframe(
        self, state: _ControllerState, target: np.ndarray, t: float
    ) -> bytes:
        words = p.pack_keyframe_words(target)
        # Mirror the decoder exactly: our new model state is what the decoder
        # will reconstruct from the words, not the pre-quantization target.
        state.q, state.v = predictor.apply_keyframe(p.unpack_keyframe_words(words))
        state.need_keyframe = False
        payload = np.asarray(words, dtype="<u2").tobytes()
        return p.build_frame(p.FRAME_KEYFRAME, state.controller, t, payload)

    def _encode_delta(
        self, state: _ControllerState, target: np.ndarray, t: float
    ) -> bytes:
        _, err, corr = predictor.error_to_target(state.q, state.v, target)
        weights = np.array(p.ERROR_WEIGHTS, dtype=np.int64)
        scores = np.abs(err.astype(np.int64)) @ weights
        nonzero_corr = np.any(corr != 0, axis=1)
        candidates = np.flatnonzero((scores > 0) & nonzero_corr)

        max_ops = candidates.size
        if self.config.budget_bytes is not None:
            overhead = p.HEADER.size + p.CRC_STRUCT.size + 2  # + n_ops field
            room = max(0, self.config.budget_bytes - overhead)
            max_ops = min(max_ops, room // p.DELTA_OP_COST_ESTIMATE)

        if max_ops < candidates.size:
            order = np.argsort(-scores[candidates], kind="stable")
            chosen = candidates[order[:max_ops]]
            chosen.sort()
        else:
            chosen = candidates

        corr_chosen = corr[chosen]
        words = p.pack_delta_words(corr_chosen)
        payload = p.build_delta_payload(chosen, words)
        # Mirror the decoder: every light coasts; chosen lights apply corr.
        state.q, state.v = predictor.apply_delta(state.q, state.v, chosen, corr_chosen)
        self.stats.ops_sent += int(chosen.size)
        return p.build_frame(p.FRAME_DELTA, state.controller, t, payload)

    # -------------------------------------------------------------------- state

    def model_oklch(self, controller: int) -> np.ndarray:
        """The encoder's model of the decoder's current colors (for tests/stats)."""
        oklch: np.ndarray = p.dequantize(self.states[controller].q)
        return oklch


@dataclass
class _DecoderChannel:
    length: int
    kinds: np.ndarray  # (length,) uint8
    weights: np.ndarray  # (length,) uint8
    active_positions: np.ndarray  # (n_active,) strip indices
    prev_active: np.ndarray  # per-strip-position bounding actives (interp only)
    next_active: np.ndarray


@dataclass
class _DecoderController:
    channels: Dict[int, _DecoderChannel] = field(default_factory=dict)
    active_order: List[Tuple[int, int]] = field(default_factory=list)
    q: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int32))
    v: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int32))
    brightness: int = 255
    color_correction: Tuple[int, int, int] = (255, 255, 255)
    synced: bool = False  # becomes True at first KEYFRAME


class Decoder:
    """Reference decoder (spec §11.8.1): consumes wire bytes, exposes state.

    Feed whole frames via :meth:`decode`, or a raw byte stream via
    :meth:`feed`. Initializes purely from SESSION frames — exactly the
    information a Scorpio has.
    """

    def __init__(self) -> None:
        self.controllers: Dict[int, _DecoderController] = {}
        self.want_resync = False
        self.last_t: float = float("nan")
        self._splitter = p.FrameSplitter()

    # ------------------------------------------------------------------- input

    def feed(self, data: bytes) -> List[Tuple[int, int]]:
        """Feed stream bytes; returns [(frame_type, controller)] applied.

        CRC/framing errors set ``want_resync`` (spec §13.2.7) and skip the
        bad frame rather than raising.
        """
        applied = []
        for raw in self._splitter.feed(data):
            try:
                applied.append(self.decode(raw, cobs_decoded=True))
            except p.ProtocolError:
                self.want_resync = True
        return applied

    def decode(self, frame: bytes, cobs_decoded: bool = False) -> Tuple[int, int]:
        """Decode one frame (with or without COBS+delimiter); apply it."""
        raw = frame
        if not cobs_decoded:
            raw = p.cobs_decode(frame.rstrip(b"\x00"))
        frame_type, controller, t, payload = p.parse_frame(raw)
        self.last_t = t
        if frame_type == p.FRAME_SESSION:
            self._apply_session(controller, payload)
        elif frame_type == p.FRAME_KEYFRAME:
            self._apply_keyframe(controller, payload)
        elif frame_type == p.FRAME_DELTA:
            self._apply_delta(controller, payload)
        else:
            raise p.ProtocolError(f"Unexpected frame type {frame_type}")
        return frame_type, controller

    # ------------------------------------------------------------------ applies

    def _controller(self, controller: int) -> _DecoderController:
        if controller not in self.controllers:
            raise p.ProtocolError(
                f"Frame for controller {controller} before its SESSION"
            )
        return self.controllers[controller]

    def _apply_session(self, controller: int, payload: bytes) -> None:
        session = p.parse_session_payload(payload)
        state = _DecoderController(
            brightness=session["brightness"],
            color_correction=session["color_correction"],
        )
        active_order: List[Tuple[int, int]] = []
        for channel in sorted(session["channels"]):
            info = session["channels"][channel]
            kinds = info["kinds"]
            active_positions = np.flatnonzero(kinds == Kind.ACTIVE)
            prev_active = np.full(info["length"], -1, dtype=np.int64)
            next_active = np.full(info["length"], -1, dtype=np.int64)
            if active_positions.size:
                idx = np.arange(info["length"])
                prev_ptr = np.searchsorted(active_positions, idx, side="right") - 1
                next_ptr = np.searchsorted(active_positions, idx, side="left")
                valid_prev = prev_ptr >= 0
                valid_next = next_ptr < active_positions.size
                prev_active[valid_prev] = active_positions[prev_ptr[valid_prev]]
                next_active[valid_next] = active_positions[next_ptr[valid_next]]
            state.channels[channel] = _DecoderChannel(
                length=info["length"],
                kinds=kinds,
                weights=info["weights"],
                active_positions=active_positions,
                prev_active=prev_active,
                next_active=next_active,
            )
            active_order.extend((channel, int(pos)) for pos in active_positions)
        state.active_order = active_order
        state.q, state.v = predictor.new_state(len(active_order))
        self.controllers[controller] = state

    def _apply_keyframe(self, controller: int, payload: bytes) -> None:
        state = self._controller(controller)
        words = np.frombuffer(payload, dtype="<u2")
        if words.shape[0] != state.q.shape[0]:
            raise p.ProtocolError(
                f"KEYFRAME has {words.shape[0]} lights, session says {state.q.shape[0]}"
            )
        state.q, state.v = predictor.apply_keyframe(p.unpack_keyframe_words(words))
        state.synced = True

    def _apply_delta(self, controller: int, payload: bytes) -> None:
        state = self._controller(controller)
        positions, words = p.parse_delta_payload(payload)
        if positions.size and int(positions.max()) >= state.q.shape[0]:
            raise p.ProtocolError("DELTA op position out of range")
        corrections = p.unpack_delta_words(words)
        state.q, state.v = predictor.apply_delta(
            state.q, state.v, positions, corrections
        )

    # ------------------------------------------------------------------ outputs

    def active_oklch(self, controller: int) -> np.ndarray:
        """(n_active,3) float OKLCH of ACTIVE lights, canonical order."""
        oklch: np.ndarray = p.dequantize(self._controller(controller).q)
        return oklch

    def active_q(self, controller: int) -> np.ndarray:
        """(n_active,3) int32 quantized state (golden-vector unit)."""
        q: np.ndarray = self._controller(controller).q.copy()
        return q

    def strip_oklch(self, controller: int, channel: int) -> np.ndarray:
        """(strip_len,3) OKLCH for a whole strip with interpolation applied.

        ACTIVE positions take their decoded value; INTERPOLATED positions
        blend bounding actives in OKLCH with shortest-arc hue (spec §13.5.1);
        INACTIVE positions are black. This mirrors firmware/JS output.
        """
        state = self._controller(controller)
        ch = state.channels[channel]
        base = 0
        for other in sorted(state.channels):
            if other == channel:
                break
            base += int(state.channels[other].active_positions.size)

        out_q = np.zeros((ch.length, 3), dtype=np.float64)
        slot_of_position = {
            int(pos): base + i for i, pos in enumerate(ch.active_positions)
        }
        for pos, slot in slot_of_position.items():
            out_q[pos] = state.q[slot]

        interp_positions = np.flatnonzero(ch.kinds == Kind.INTERPOLATED)
        for pos in (int(v) for v in interp_positions):
            prev_pos, next_pos = ch.prev_active[pos], ch.next_active[pos]
            if prev_pos < 0 or next_pos < 0:
                continue  # loader forbids this; be safe on wire data anyway
            w = ch.weights[pos] / 255.0
            q_prev = state.q[slot_of_position[int(prev_pos)]].astype(np.float64)
            q_next = state.q[slot_of_position[int(next_pos)]].astype(np.float64)
            blended = q_prev + w * (q_next - q_prev)
            d_h = float(
                predictor.hue_wrap_diff(
                    np.array([int(q_next[2])]), np.array([int(q_prev[2])])
                )[0]
            )
            blended[2] = (q_prev[2] + w * d_h) % p.QH_MOD
            out_q[pos] = blended

        return p.dequantize(out_q)
