// Print the mapping page's key -> event map as JSON. Conformance:
// tests/test_mapping_keys.py holds this map and the TUI's byte tables
// to one canonical contract (the golden-vector philosophy, applied to
// key handling).
//
//   node tests/js/print_mapping_keys.mjs

import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const path = join(
  here, "..", "..", "luminary", "server", "static", "mapping.js"
);
const { KEYS } = await import(pathToFileURL(path).href);
console.log(JSON.stringify(KEYS));
