"""Protocol constants, framing, and quantization (spec §11).

Everything on this page is normative for all three decoder implementations
(Python reference, JavaScript, C++); the golden vectors (spec §11.9) hold them
to it. Byte order is little-endian throughout.

Frame envelope (spec §11.7.1):
    [version u8][type u8][controller u8][t f64][payload_len u16]
    [payload ...][crc16 u16]
CRC16 is CCITT-FALSE (poly 0x1021, init 0xFFFF) over header+payload. The whole
buffer is then COBS-encoded and terminated with a 0x00 delimiter, identically
on serial and WebSocket transports.

Per-light wire format (spec §11.4):
  - internal quantized state: qL 6 bits / qC 5 bits / qH 8 bits
  - KEYFRAME word:  [L5|C4|H7]                 (top significant bits)
  - DELTA word:     [sL|mL4|sC|mC3|sH|mH6]     (sign+magnitude corrections)
"""

from __future__ import annotations

import struct
from typing import Iterator, List, Tuple

import numpy as np

PROTOCOL_VERSION = 1

# Frame types (spec §11.7.2; HELLO/RESYNC are device->host, spec §13.3)
FRAME_SESSION = 0
FRAME_KEYFRAME = 1
FRAME_DELTA = 2
FRAME_HELLO = 3
FRAME_RESYNC = 4
FRAME_ACK = 5

# Quantized precision (spec §11.4.1)
QL_LEVELS = 64  # 6 bits over L in [0, 1]
QC_LEVELS = 32  # 5 bits over C in [0, C_MAX]
QH_MOD = 256  # 8 bits over H in [0, 360), wrapping
C_MAX = 0.4

# Delta correction magnitude limits (spec §11.4.3)
DELTA_MAX = (15, 7, 63)  # L, C, H (sign+4 / sign+3 / sign+6)

# Predictor fixed point (spec §11.5.4)
V_SHIFT = 3  # velocity is in 1/8-LSB units
V_ROUND = 4  # rounding constant for prediction
ALPHA_SHIFT = 2  # velocity blend alpha = 1/4

# Error ranking weights, L/C/H (spec §11.6.2)
ERROR_WEIGHTS = (3, 2, 1)

HEADER = struct.Struct("<BBBdH")  # version, type, controller, t, payload_len
CRC_STRUCT = struct.Struct("<H")

BYTES_PER_LIGHT = 2  # both KEYFRAME and DELTA words (spec §11.4.3)
DELTA_OP_COST_ESTIMATE = 3  # varint skip (usually 1 byte) + 2-byte word


class ProtocolError(ValueError):
    """Raised on malformed, corrupt, or unsupported wire data."""


# --------------------------------------------------------------------- CRC16

_CRC_TABLE = np.zeros(256, dtype=np.uint16)
for _byte in range(256):
    _crc = _byte << 8
    for _ in range(8):
        _crc = ((_crc << 1) ^ 0x1021) if (_crc & 0x8000) else (_crc << 1)
    _CRC_TABLE[_byte] = _crc & 0xFFFF


def crc16(data: bytes) -> int:
    """CRC16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection or xor-out."""
    crc = 0xFFFF
    table = _CRC_TABLE
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ int(table[((crc >> 8) ^ b) & 0xFF])
    return crc


# --------------------------------------------------------------------- COBS


def cobs_encode(data: bytes) -> bytes:
    """Consistent Overhead Byte Stuffing; output contains no 0x00 bytes."""
    out = bytearray()
    idx = 0
    n = len(data)
    while True:
        block_end = data.find(b"\x00", idx)
        if block_end == -1:
            block_end = n
        while block_end - idx >= 254:
            out.append(0xFF)
            out.extend(data[idx : idx + 254])
            idx += 254
        out.append(block_end - idx + 1)
        out.extend(data[idx:block_end])
        if block_end >= n:
            break
        idx = block_end + 1
        if idx == n:  # trailing zero encodes as an extra empty block
            out.append(0x01)
            break
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """Inverse of :func:`cobs_encode`; input must not contain 0x00."""
    out = bytearray()
    idx = 0
    n = len(data)
    while idx < n:
        code = data[idx]
        if code == 0:
            raise ProtocolError("COBS data contains a zero byte")
        block = data[idx + 1 : idx + code]
        if len(block) != code - 1:
            raise ProtocolError("Truncated COBS block")
        out.extend(block)
        idx += code
        if code != 0xFF and idx < n:
            out.append(0)
    return bytes(out)


def cobs_decode_header(data: bytes) -> bytes:
    """COBS-decode only the leading :data:`HEADER` bytes of a frame body.

    The driver needs the controller and ``t`` out of every outbound frame to
    route and track it, but running the full :func:`cobs_decode` for that is
    O(frame) Python per frame — at production frame sizes it costs more than
    rendering and encoding the frame did. This stops once the header is out,
    which is O(1) in the payload size.

    Returns at least ``HEADER.size`` bytes when the input is long enough;
    callers must not assume anything past that is present.
    """
    out = bytearray()
    idx = 0
    n = len(data)
    while idx < n and len(out) < HEADER.size:
        code = data[idx]
        if code == 0:
            raise ProtocolError("COBS data contains a zero byte")
        block = data[idx + 1 : idx + code]
        if len(block) != code - 1:
            raise ProtocolError("Truncated COBS block")
        out.extend(block)
        idx += code
        if code != 0xFF and idx < n:
            out.append(0)
    if len(out) < HEADER.size:
        raise ProtocolError(f"Frame shorter than a header: {len(out)} bytes")
    return bytes(out)


# --------------------------------------------------------------------- frames


def build_frame(frame_type: int, controller: int, t: float, payload: bytes) -> bytes:
    """Assemble header+payload+crc, COBS-encode, append the 0x00 delimiter."""
    if len(payload) > 0xFFFF:
        raise ProtocolError(f"Payload too large: {len(payload)} bytes")
    raw = HEADER.pack(PROTOCOL_VERSION, frame_type, controller, t, len(payload))
    raw += payload
    raw += CRC_STRUCT.pack(crc16(raw))
    return cobs_encode(raw) + b"\x00"


def build_ack(controller: int, t: float) -> bytes:
    """ACK the frame whose header time was ``t`` (spec §11.7.6).

    The acknowledged time rides in this frame's own header ``t`` field, so the
    ACK carries no payload. Acknowledging ``t`` retires every frame at or
    before it, which makes a dropped ACK self-correcting: the next one
    re-establishes the true position rather than leaving the sender's window
    permanently short.
    """
    return build_frame(FRAME_ACK, controller, t, b"")


def parse_frame(raw: bytes) -> Tuple[int, int, float, bytes]:
    """Parse a COBS-decoded frame body -> (type, controller, t, payload)."""
    if len(raw) < HEADER.size + CRC_STRUCT.size:
        raise ProtocolError(f"Frame too short: {len(raw)} bytes")
    body, crc_bytes = raw[: -CRC_STRUCT.size], raw[-CRC_STRUCT.size :]
    (expected,) = CRC_STRUCT.unpack(crc_bytes)
    if crc16(body) != expected:
        raise ProtocolError("CRC mismatch")
    version, frame_type, controller, t, payload_len = HEADER.unpack(body[: HEADER.size])
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported protocol version {version}")
    payload = body[HEADER.size :]
    if len(payload) != payload_len:
        raise ProtocolError(
            f"Payload length mismatch: header says {payload_len}, got {len(payload)}"
        )
    return frame_type, controller, t, payload


class FrameSplitter:
    """Accumulates a byte stream and yields COBS-delimited frame bodies.

    Corrupt frames raise :class:`ProtocolError` from :func:`parse_frame` at the
    caller; the splitter itself just resynchronizes on 0x00 delimiters
    (spec §11.7.1).
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> Iterator[bytes]:
        self._buffer.extend(data)
        while True:
            try:
                delim = self._buffer.index(0)
            except ValueError:
                return
            chunk = bytes(self._buffer[:delim])
            del self._buffer[: delim + 1]
            if chunk:  # empty chunks are keepalive/no-ops
                yield cobs_decode(chunk)


# --------------------------------------------------------------- quantization


def quantize(oklch: np.ndarray) -> np.ndarray:
    """(n,3) float OKLCH -> (n,3) int32 quantized [qL, qC, qH] (spec §11.4.1)."""
    oklch = np.nan_to_num(oklch, nan=0.0)
    q = np.empty((oklch.shape[0], 3), dtype=np.int32)
    q[:, 0] = np.clip(np.rint(oklch[:, 0] * (QL_LEVELS - 1)), 0, QL_LEVELS - 1)
    q[:, 1] = np.clip(np.rint(oklch[:, 1] / C_MAX * (QC_LEVELS - 1)), 0, QC_LEVELS - 1)
    q[:, 2] = np.rint(oklch[:, 2] / 360.0 * QH_MOD).astype(np.int64) % QH_MOD
    return q


def dequantize(q: np.ndarray) -> np.ndarray:
    """(n,3) int quantized -> (n,3) float OKLCH."""
    out = np.empty((q.shape[0], 3), dtype=np.float64)
    out[:, 0] = q[:, 0] / (QL_LEVELS - 1)
    out[:, 1] = q[:, 1] / (QC_LEVELS - 1) * C_MAX
    out[:, 2] = q[:, 2] / QH_MOD * 360.0
    return out


# ------------------------------------------------------------ keyframe words


def pack_keyframe_words(q: np.ndarray) -> np.ndarray:
    """(n,3) quantized -> (n,) uint16 keyframe words [L5|C4|H7] (spec §11.4.2)."""
    k_l = np.minimum((q[:, 0] + 1) >> 1, 31)
    k_c = np.minimum((q[:, 1] + 1) >> 1, 15)
    k_h = ((q[:, 2] + 1) >> 1) & 127
    out: np.ndarray = ((k_l << 11) | (k_c << 7) | k_h).astype(np.uint16)
    return out


def unpack_keyframe_words(words: np.ndarray) -> np.ndarray:
    """(n,) uint16 -> (n,3) int32 quantized values (bottom bit zero)."""
    w = words.astype(np.int32)
    q = np.empty((w.shape[0], 3), dtype=np.int32)
    q[:, 0] = (w >> 11) << 1
    q[:, 1] = ((w >> 7) & 15) << 1
    q[:, 2] = (w & 127) << 1
    return q


# --------------------------------------------------------------- delta words


def pack_delta_words(corr: np.ndarray) -> np.ndarray:
    """(m,3) int32 corrections -> (m,) uint16 [sL|mL4|sC|mC3|sH|mH6].

    Corrections must already be saturated to DELTA_MAX; sign bit 1 = negative.
    """
    mags = np.abs(corr)
    signs = (corr < 0).astype(np.int32)
    if (
        np.any(mags[:, 0] > DELTA_MAX[0])
        or np.any(mags[:, 1] > DELTA_MAX[1])
        or np.any(mags[:, 2] > DELTA_MAX[2])
    ):
        raise ProtocolError("Delta correction exceeds field range")
    word = (
        (signs[:, 0] << 15)
        | (mags[:, 0] << 11)
        | (signs[:, 1] << 10)
        | (mags[:, 1] << 7)
        | (signs[:, 2] << 6)
        | mags[:, 2]
    )
    out: np.ndarray = word.astype(np.uint16)
    return out


def unpack_delta_words(words: np.ndarray) -> np.ndarray:
    """(m,) uint16 -> (m,3) int32 signed corrections."""
    w = words.astype(np.int32)
    corr = np.empty((w.shape[0], 3), dtype=np.int32)
    m_l = (w >> 11) & 15
    m_c = (w >> 7) & 7
    m_h = w & 63
    corr[:, 0] = np.where((w >> 15) & 1, -m_l, m_l)
    corr[:, 1] = np.where((w >> 10) & 1, -m_c, m_c)
    corr[:, 2] = np.where((w >> 6) & 1, -m_h, m_h)
    return corr


# -------------------------------------------------------------------- varint


def encode_varint(value: int) -> bytes:
    """Unsigned LEB128."""
    if value < 0:
        raise ProtocolError("varint must be non-negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """Decode LEB128 at offset -> (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ProtocolError("Truncated varint")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, offset
        shift += 7
        if shift > 28:
            raise ProtocolError("Varint too long")


# ----------------------------------------------------------- session payload


def build_session_payload(
    channel_strips: dict,
    brightness: int,
    color_correction: Tuple[int, int, int],
) -> bytes:
    """SESSION payload (spec §11.7.2): full strip map + output calibration."""
    out = bytearray()
    out.append(len(channel_strips))
    for channel in sorted(channel_strips):
        strip = channel_strips[channel]
        length = int(strip["length"])
        out.append(channel)
        out.extend(struct.pack("<H", length))
        kinds = np.asarray(strip["kinds"], dtype=np.uint8)
        weights = np.asarray(strip["weights"], dtype=np.uint8)
        interleaved = np.empty(length * 2, dtype=np.uint8)
        interleaved[0::2] = kinds
        interleaved[1::2] = weights
        out.extend(interleaved.tobytes())
    out.append(brightness & 0xFF)
    out.extend(bytes(c & 0xFF for c in color_correction))
    return bytes(out)


def parse_session_payload(payload: bytes) -> dict:
    """Inverse of :func:`build_session_payload`."""
    offset = 0
    if len(payload) < 1:
        raise ProtocolError("Empty SESSION payload")
    n_channels = payload[offset]
    offset += 1
    channels = {}
    for _ in range(n_channels):
        if offset + 3 > len(payload):
            raise ProtocolError("Truncated SESSION channel header")
        channel = payload[offset]
        (length,) = struct.unpack_from("<H", payload, offset + 1)
        offset += 3
        end = offset + length * 2
        if end > len(payload):
            raise ProtocolError("Truncated SESSION strip map")
        interleaved = np.frombuffer(payload[offset:end], dtype=np.uint8)
        channels[channel] = {
            "length": length,
            "kinds": interleaved[0::2].copy(),
            "weights": interleaved[1::2].copy(),
        }
        offset = end
    if offset + 4 > len(payload):
        raise ProtocolError("Truncated SESSION calibration block")
    brightness = payload[offset]
    color_correction = tuple(payload[offset + 1 : offset + 4])
    return {
        "channels": channels,
        "brightness": brightness,
        "color_correction": color_correction,
    }


# ----------------------------------------------------------- delta payload


def build_delta_payload(positions: np.ndarray, words: np.ndarray) -> bytes:
    """DELTA payload: [n_ops u16] then (varint skip, u16 word) per op.

    ``positions`` are ascending active-slot indices; skip semantics
    (spec §11.7.4): first op is at slot = skip; each subsequent op is at
    slot = previous + 1 + skip.
    """
    out = bytearray(struct.pack("<H", len(positions)))
    prev = -1
    words_le = words.astype("<u2")
    for pos, word in zip(positions.tolist(), words_le.tolist()):
        out.extend(encode_varint(pos - prev - 1))
        out.extend(struct.pack("<H", word))
        prev = pos
    return bytes(out)


def parse_delta_payload(payload: bytes) -> Tuple[np.ndarray, np.ndarray]:
    """Inverse of :func:`build_delta_payload` -> (positions, words)."""
    if len(payload) < 2:
        raise ProtocolError("Truncated DELTA payload")
    (n_ops,) = struct.unpack_from("<H", payload, 0)
    offset = 2
    positions: List[int] = []
    words: List[int] = []
    prev = -1
    for _ in range(n_ops):
        skip, offset = decode_varint(payload, offset)
        if offset + 2 > len(payload):
            raise ProtocolError("Truncated DELTA op")
        (word,) = struct.unpack_from("<H", payload, offset)
        offset += 2
        pos = prev + 1 + skip
        positions.append(pos)
        words.append(word)
        prev = pos
    if offset != len(payload):
        raise ProtocolError("Trailing bytes in DELTA payload")
    return np.array(positions, dtype=np.int64), np.array(words, dtype=np.uint16)
