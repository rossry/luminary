"""Seed a store with demo geometries so a fresh server isn't empty.

Used by ``luminary.cli seed`` and ``luminary.cli serve --seed-demo`` (one
implementation, two triggers). Content-hash ids make seeding idempotent:
re-running against an already-seeded store changes nothing (spec §15.6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from luminary.geometry.capture.from_scaffold import CaptureParams, capture
from luminary.geometry.scaffold import Scaffold
from luminary.server.store import Store

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def seed_store(store_dir: Path) -> List[Dict[str, str]]:
    """Load the demo scaffold + captured lights (and the pentagon, if its
    config is present) into ``store_dir``. Returns [{kind, id, name}]."""
    store = Store(store_dir)
    seeded: List[Dict[str, str]] = []

    scaffold_doc = json.loads((_EXAMPLES / "hex-demo.scaffold.json").read_text())
    scaffold_id = store.save("scaffolds", scaffold_doc)
    seeded.append({"kind": "scaffold", "id": scaffold_id, "name": "hex-demo"})

    scaffold = Scaffold.load(scaffold_doc)
    lights = capture(scaffold, CaptureParams(count_per_line=24, interpolate_every=3))
    lights_doc = lights.to_file_dict()
    lights_doc["meta"]["name"] = "hex-demo"
    lights_doc["source"]["scaffold"] = scaffold_id
    lights_id = store.save("lights", lights_doc)
    seeded.append({"kind": "lights", "id": lights_id, "name": "hex-demo"})

    for config_name in ("4A-35", "4A-33"):
        pentagon_config = _CONFIGS / f"{config_name}.json"
        if not pentagon_config.exists():
            continue
        from luminary.geometry.net import Net
        from luminary.geometry.pentagon import capture as pentagon_capture

        pentagon = pentagon_capture(Net.from_json_file(pentagon_config))
        pentagon_doc = pentagon.to_file_dict()
        name = f"pentagon-{config_name}"
        pentagon_doc["meta"]["name"] = name
        pentagon_id = store.save("lights", pentagon_doc)
        seeded.append({"kind": "lights", "id": pentagon_id, "name": name})

    return seeded
