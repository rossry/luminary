/* Luminary wire decoder — JavaScript conformance implementation (spec §14.2).
 *
 * Mirrors luminary/comms/{protocol,predictor}.py and the C++ lumicodec
 * bit-for-bit: int32 arithmetic, arithmetic shifts, hue on the mod-256 ring.
 * Verified against the shared golden vectors (spec §11.9).
 */

export const FRAME_SESSION = 0;
export const FRAME_KEYFRAME = 1;
export const FRAME_DELTA = 2;

const HEADER_SIZE = 13; // u8 version, u8 type, u8 controller, f64 t, u16 len
const PROTOCOL_VERSION = 1;

const KIND_ACTIVE = 0;
const KIND_INTERPOLATED = 1;

// ---------------------------------------------------------------- CRC16

const CRC_TABLE = new Uint16Array(256);
for (let byte = 0; byte < 256; byte++) {
  let crc = byte << 8;
  for (let i = 0; i < 8; i++) {
    crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
  }
  CRC_TABLE[byte] = crc;
}

export function crc16(bytes) {
  let crc = 0xffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = ((crc << 8) & 0xffff) ^ CRC_TABLE[((crc >> 8) ^ bytes[i]) & 0xff];
  }
  return crc;
}

// ---------------------------------------------------------------- COBS

export function cobsDecode(data) {
  const out = [];
  let idx = 0;
  while (idx < data.length) {
    const code = data[idx];
    if (code === 0) throw new Error("COBS: zero byte in data");
    if (idx + code > data.length + 1) throw new Error("COBS: truncated block");
    for (let i = 1; i < code; i++) out.push(data[idx + i]);
    idx += code;
    if (code !== 0xff && idx < data.length) out.push(0);
  }
  return Uint8Array.from(out);
}

// ------------------------------------------------------------- predictor

function hueWrapDiff(a, b) {
  return (((a - b + 128) & 255) - 128) | 0;
}

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

/* One DELTA step over a controller's (q, v) state (spec §11.5.4). */
function applyDelta(q, v, positions, corrections) {
  const n = q.length / 3;
  const corrByPos = positions ? new Map() : null;
  if (positions) {
    for (let i = 0; i < positions.length; i++) {
      corrByPos.set(positions[i], [
        corrections[i * 3],
        corrections[i * 3 + 1],
        corrections[i * 3 + 2],
      ]);
    }
  }
  for (let i = 0; i < n; i++) {
    const qL = q[i * 3], qC = q[i * 3 + 1], qH = q[i * 3 + 2];
    let pL = clamp((qL + ((v[i * 3] + 4) >> 3)) | 0, 0, 63);
    let pC = clamp((qC + ((v[i * 3 + 1] + 4) >> 3)) | 0, 0, 31);
    let pH = (qH + ((v[i * 3 + 2] + 4) >> 3)) & 255;
    const corr = corrByPos ? corrByPos.get(i) : undefined;
    if (corr !== undefined) {
      pL = clamp(pL + corr[0], 0, 63);
      pC = clamp(pC + corr[1], 0, 31);
      pH = (pH + corr[2]) & 255;
    }
    const dL = (pL - qL) | 0;
    const dC = (pC - qC) | 0;
    const dH = hueWrapDiff(pH, qH);
    v[i * 3] = (v[i * 3] + (((dL << 3) - v[i * 3]) >> 2)) | 0;
    v[i * 3 + 1] = (v[i * 3 + 1] + (((dC << 3) - v[i * 3 + 1]) >> 2)) | 0;
    v[i * 3 + 2] = (v[i * 3 + 2] + (((dH << 3) - v[i * 3 + 2]) >> 2)) | 0;
    q[i * 3] = pL;
    q[i * 3 + 1] = pC;
    q[i * 3 + 2] = pH;
  }
}

// --------------------------------------------------------------- decoder

export class LumiDecoder {
  constructor() {
    this.controllers = new Map();
    this.wantResync = false;
    this.lastT = NaN;
    this._pending = [];
  }

  /* Feed raw stream bytes; returns [{type, controller}] for applied frames. */
  feed(bytes) {
    const applied = [];
    for (let i = 0; i < bytes.length; i++) {
      if (bytes[i] === 0) {
        if (this._pending.length) {
          const chunk = Uint8Array.from(this._pending);
          this._pending.length = 0;
          try {
            applied.push(this.decodeFrame(cobsDecode(chunk)));
          } catch (err) {
            this.wantResync = true;
          }
        }
      } else {
        this._pending.push(bytes[i]);
      }
    }
    return applied;
  }

  /* Decode one COBS-decoded frame body. */
  decodeFrame(raw) {
    if (raw.length < HEADER_SIZE + 2) throw new Error("frame too short");
    const body = raw.subarray(0, raw.length - 2);
    const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    const expected = view.getUint16(raw.length - 2, true);
    if (crc16(body) !== expected) throw new Error("CRC mismatch");
    const version = raw[0];
    if (version !== PROTOCOL_VERSION) throw new Error("bad version");
    const type = raw[1];
    const controller = raw[2];
    this.lastT = view.getFloat64(3, true);
    const payloadLen = view.getUint16(11, true);
    const payload = raw.subarray(HEADER_SIZE, HEADER_SIZE + payloadLen);
    if (payload.length !== payloadLen) throw new Error("length mismatch");

    if (type === FRAME_SESSION) this._applySession(controller, payload);
    else if (type === FRAME_KEYFRAME) this._applyKeyframe(controller, payload);
    else if (type === FRAME_DELTA) this._applyDelta(controller, payload);
    else throw new Error(`unexpected frame type ${type}`);
    return { type, controller };
  }

  _state(controller) {
    const state = this.controllers.get(controller);
    if (!state) throw new Error(`frame before SESSION for controller ${controller}`);
    return state;
  }

  _applySession(controller, payload) {
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    let off = 0;
    const nChannels = payload[off++];
    const channels = new Map();
    let nActive = 0;
    for (let c = 0; c < nChannels; c++) {
      const channel = payload[off];
      const length = view.getUint16(off + 1, true);
      off += 3;
      const kinds = new Uint8Array(length);
      const weights = new Uint8Array(length);
      const activePositions = [];
      for (let i = 0; i < length; i++) {
        kinds[i] = payload[off + i * 2];
        weights[i] = payload[off + i * 2 + 1];
        if (kinds[i] === KIND_ACTIVE) activePositions.push(i);
      }
      off += length * 2;
      channels.set(channel, {
        length,
        kinds,
        weights,
        activePositions: Int32Array.from(activePositions),
        base: nActive,
      });
      nActive += activePositions.length;
    }
    const brightness = payload[off];
    const colorCorrection = [payload[off + 1], payload[off + 2], payload[off + 3]];
    this.controllers.set(controller, {
      channels,
      nActive,
      q: new Int32Array(nActive * 3),
      v: new Int32Array(nActive * 3),
      brightness,
      colorCorrection,
      synced: false,
    });
  }

  _applyKeyframe(controller, payload) {
    const state = this._state(controller);
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const n = payload.length / 2;
    if (n !== state.nActive) throw new Error("keyframe size mismatch");
    for (let i = 0; i < n; i++) {
      const word = view.getUint16(i * 2, true);
      state.q[i * 3] = ((word >> 11) & 31) << 1;
      state.q[i * 3 + 1] = ((word >> 7) & 15) << 1;
      state.q[i * 3 + 2] = (word & 127) << 1;
      state.v[i * 3] = 0;
      state.v[i * 3 + 1] = 0;
      state.v[i * 3 + 2] = 0;
    }
    state.synced = true;
  }

  _applyDelta(controller, payload) {
    const state = this._state(controller);
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const nOps = view.getUint16(0, true);
    let off = 2;
    const positions = new Int32Array(nOps);
    const corrections = new Int32Array(nOps * 3);
    let prev = -1;
    for (let i = 0; i < nOps; i++) {
      let skip = 0;
      let shift = 0;
      for (;;) {
        if (off >= payload.length) throw new Error("truncated varint");
        const byte = payload[off++];
        skip |= (byte & 0x7f) << shift;
        if (!(byte & 0x80)) break;
        shift += 7;
      }
      if (off + 2 > payload.length) throw new Error("truncated delta op");
      const word = view.getUint16(off, true);
      off += 2;
      const pos = prev + 1 + skip;
      if (pos >= state.nActive) throw new Error("delta position out of range");
      positions[i] = pos;
      prev = pos;
      const mL = (word >> 11) & 15;
      const mC = (word >> 7) & 7;
      const mH = word & 63;
      corrections[i * 3] = (word >> 15) & 1 ? -mL : mL;
      corrections[i * 3 + 1] = (word >> 10) & 1 ? -mC : mC;
      corrections[i * 3 + 2] = (word >> 6) & 1 ? -mH : mH;
    }
    if (off !== payload.length) throw new Error("trailing delta bytes");
    applyDelta(state.q, state.v, positions, corrections);
  }

  /* (nActive*3) Int32Array of quantized OKLCH — the golden-vector unit. */
  activeQ(controller) {
    return this._state(controller).q;
  }

  /* Dequantized OKLCH per strip position with interpolation applied
   * (OKLCH shortest-arc, spec §13.5.1). Returns Float64Array(length*3). */
  stripOKLCH(controller, channel) {
    const state = this._state(controller);
    const ch = state.channels.get(channel);
    const out = new Float64Array(ch.length * 3);
    const slotOf = new Map();
    for (let i = 0; i < ch.activePositions.length; i++) {
      slotOf.set(ch.activePositions[i], ch.base + i);
    }
    for (let pos = 0; pos < ch.length; pos++) {
      if (ch.kinds[pos] === KIND_ACTIVE) {
        const slot = slotOf.get(pos);
        out[pos * 3] = state.q[slot * 3] / 63;
        out[pos * 3 + 1] = (state.q[slot * 3 + 1] / 31) * 0.4;
        out[pos * 3 + 2] = (state.q[slot * 3 + 2] / 256) * 360;
      } else if (ch.kinds[pos] === KIND_INTERPOLATED) {
        let prevA = -1;
        for (let i = ch.activePositions.length - 1; i >= 0; i--) {
          if (ch.activePositions[i] < pos) { prevA = ch.activePositions[i]; break; }
        }
        let nextA = -1;
        for (let i = 0; i < ch.activePositions.length; i++) {
          if (ch.activePositions[i] > pos) { nextA = ch.activePositions[i]; break; }
        }
        if (prevA < 0 || nextA < 0) continue;
        const w = ch.weights[pos] / 255;
        const a = slotOf.get(prevA) * 3;
        const b = slotOf.get(nextA) * 3;
        const qL = state.q[a] + w * (state.q[b] - state.q[a]);
        const qC = state.q[a + 1] + w * (state.q[b + 1] - state.q[a + 1]);
        const dH = hueWrapDiff(state.q[b + 2], state.q[a + 2]);
        let qH = state.q[a + 2] + w * dH;
        qH = ((qH % 256) + 256) % 256;
        out[pos * 3] = qL / 63;
        out[pos * 3 + 1] = (qC / 31) * 0.4;
        out[pos * 3 + 2] = (qH / 256) * 360;
      }
      // INACTIVE stays black (zeros).
    }
    return out;
  }
}
