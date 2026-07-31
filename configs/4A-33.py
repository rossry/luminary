#!/usr/bin/env python3
"""Generate 4A-33.json: 4A-35 minus the tip triangle of each upper arm.

Derived from 4A-35.json rather than re-generated, so the relationship is
explicit: everything is identical except the topmost triangle of the
up-right arm (series 0) and of the up-left arm (series 4) are removed
(35 -> 33 triangles; series sizes [7,9,3,9,7] -> [6,9,3,9,6]).

Points 23 and 26 (the removed tips' outer vertices) become unused but are
kept so every other triangle's point indices stay valid.
"""

import json
from pathlib import Path

# The two upper-arm tip triangles of 4A-35, by exact vertex indices:
#   series 0 (up-right arm), triangle [23, 15, 19]
#   series 4 (up-left arm),  triangle [26, 18, 22]
REMOVED = [(0, [23, 15, 19]), (4, [26, 18, 22])]


def main() -> None:
    script_dir = Path(__file__).parent
    config = json.loads((script_dir / "4A-35.json").read_text())

    triangles = config["geometry"]["triangles"]
    for series_idx, verts in REMOVED:
        before = len(triangles[series_idx])
        triangles[series_idx] = [t for t in triangles[series_idx] if t != verts]
        assert (
            len(triangles[series_idx]) == before - 1
        ), f"expected exactly one triangle {verts} in series {series_idx}"

    total = sum(len(s) for s in triangles)
    assert total == 33, f"expected 33 triangles, got {total}"

    output = script_dir / "4A-33.json"
    output.write_text(json.dumps(config, indent=2))
    print(f"Generated {output}")
    print(f"Series sizes: {[len(s) for s in triangles]} (total {total})")


if __name__ == "__main__":
    main()
