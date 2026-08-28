// Presentation clock conformance (spec §13.9): the browser implementation
// replays the same golden vector as the Python reference and the C++
// firmware, so the boards, the web viewer and the local preview cannot
// disagree about when a frame is shown.
//
//   node tests/js/test_presentation.mjs

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const decoderPath = join(repo, "luminary", "server", "static", "decoder.js");
const { PresentationClock, PlayoutQueue } = await import(
  pathToFileURL(decoderPath).href
);

const doc = JSON.parse(
  readFileSync(join(repo, "firmware", "golden", "presentation", "case1.json"), "utf8")
);

const clock = new PresentationClock();
for (let i = 0; i < doc.observations.length; i++) {
  const [t, arrival] = doc.observations[i];
  clock.observe(t, arrival);
  const usable = clock.usableDelay(doc.delay_us, doc.slots);
  const got = [clock.skewUs, clock.intervalUs, usable, clock.deadline(t, usable)];
  const want = doc.expected[i];
  for (let k = 0; k < want.length; k++) {
    if (got[k] !== want[k]) {
      console.error(
        `frame ${i} field ${k}: got ${got[k]}, want ${want[k]} ` +
          `(skew/interval/usable/deadline)`
      );
      process.exit(1);
    }
  }
}

// The queue holds frames until their deadline and never beyond its depth.
const q = new PlayoutQueue(3);
if (!q.push("a", 1000) || !q.push("b", 2000) || !q.push("c", 3000)) {
  console.error("queue refused a frame inside its depth");
  process.exit(1);
}
if (q.push("d", 4000)) {
  console.error("queue accepted a frame past its depth");
  process.exit(1);
}
if (q.due(999) !== null) {
  console.error("queue released a frame before its deadline");
  process.exit(1);
}
if (q.due(1000) !== "a" || q.due(2500) !== "b" || q.due(2500) !== null) {
  console.error("queue released frames out of order or too eagerly");
  process.exit(1);
}

console.log(`OK: ${doc.observations.length} frames match the reference clock`);
