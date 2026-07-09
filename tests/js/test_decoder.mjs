// JS decoder conformance test (spec §11.9): replay the golden vectors through
// the browser decoder and assert bit-exact quantized state per frame.
//
//   node tests/js/test_decoder.mjs
//
// Run automatically from pytest when node is available (test_golden.py).

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const goldenDir = join(repo, "firmware", "golden", "case1");
const decoderPath = join(repo, "luminary", "server", "static", "decoder.js");

const { LumiDecoder, FRAME_SESSION } = await import(decoderPath);

const stream = new Uint8Array(readFileSync(join(goldenDir, "stream.bin")));
const expected = new Uint8Array(readFileSync(join(goldenDir, "expected.bin")));
const meta = JSON.parse(readFileSync(join(goldenDir, "meta.json"), "utf8"));

const decoder = new LumiDecoder();
let expectedOffset = 0;
let framesChecked = 0;

// Feed in awkward chunk sizes; check after each applied frame. Frames are
// checked per event, so we must feed at most one delimiter per call: split
// the stream on 0x00 and feed each frame in two pieces.
let offset = 0;
while (offset < stream.length) {
  let end = offset;
  while (end < stream.length && stream[end] !== 0) end++;
  if (end < stream.length) end++;
  const mid = offset + Math.floor((end - offset) / 2);
  const applied = [
    ...decoder.feed(stream.subarray(offset, mid)),
    ...decoder.feed(stream.subarray(mid, end)),
  ];
  offset = end;
  if (applied.length > 1) throw new Error("multiple frames from one wire frame");
  for (const frame of applied) {
    if (frame.type === FRAME_SESSION) continue;
    const nActive = expected[expectedOffset] | (expected[expectedOffset + 1] << 8);
    expectedOffset += 2;
    const q = decoder.activeQ(meta.controller);
    if (q.length !== nActive * 3) {
      throw new Error(`frame ${framesChecked}: nActive ${q.length / 3} != ${nActive}`);
    }
    for (let i = 0; i < nActive * 3; i++) {
      if (q[i] !== expected[expectedOffset + i]) {
        throw new Error(
          `frame ${framesChecked}: q[${i}] = ${q[i]}, want ${expected[expectedOffset + i]}`
        );
      }
    }
    expectedOffset += nActive * 3;
    framesChecked++;
  }
}

if (expectedOffset !== expected.length) {
  throw new Error(`unused expected blocks (${expectedOffset} != ${expected.length})`);
}
if (decoder.wantResync) throw new Error("resync flagged on clean stream");
if (framesChecked !== meta.n_frames) {
  throw new Error(`checked ${framesChecked} frames, expected ${meta.n_frames}`);
}
console.log(`OK: ${framesChecked} frames bit-exact (JS decoder)`);
