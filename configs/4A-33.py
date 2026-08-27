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
import math
from pathlib import Path

# The two upper-arm tip triangles of 4A-35, by exact vertex indices:
#   series 0 (up-right arm), triangle [23, 15, 19]
#   series 4 (up-left arm),  triangle [26, 18, 22]
REMOVED = [(0, [23, 15, 19]), (4, [26, 18, 22])]

SIDE = 50.0  # net lattice edge length (every triangle is equilateral)

# The fold: net point -> 3V sphere vertex id (configs/sphere3v.json) —
# the 31-point prefix of 4A-37's solved correspondence (configs/4A-37.py
# documents the derivation); 4A-33 is the same net minus the four
# lower-arm extension points. None for the two orphaned points (23, 26)
# that no triangle references.
POINT_VERTEX = [
    1,
    5,
    4,
    3,
    2,
    11,
    15,
    14,
    13,
    12,
    10,
    9,
    8,
    7,
    6,
    17,
    25,
    21,
    19,
    24,
    22,
    18,
    16,
    None,
    34,
    32,
    None,
    45,
    55,
    38,
    48,
]


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

    # ---- fold onto the 3V sphere (same checks as configs/4A-37.py) ---
    points = config["geometry"]["points"]
    sphere = json.loads((script_dir / "sphere3v.json").read_text())
    xyz = {v["id"]: v["xyz"] for v in sphere["vertices"]}
    class_of = {}
    for i, j, c in sphere["edges"]:
        class_of[(min(i, j), max(i, j))] = c
    assert len(POINT_VERTEX) == len(points)

    # Radius in net units: the net's side-50 edges average the B/C chords.
    chords = []
    for series in triangles:
        for tri in series:
            for i in range(3):
                u = POINT_VERTEX[tri[i]]
                v = POINT_VERTEX[tri[(i + 1) % 3]]
                cls = class_of.get((min(u, v), max(u, v)))
                assert cls in ("B", "C"), (
                    f"net edge {tri[i]}-{tri[(i + 1) % 3]} maps to "
                    f"{u}-{v}, not a dome strut of the panel shape"
                )
                chords.append(math.dist(xyz[u], xyz[v]))
    radius = SIDE / (sum(chords) / len(chords))
    for c in chords:
        assert 0.98 * SIDE < c * radius < 1.02 * SIDE, c * radius

    # Per-point 3D positions; mirror pairs must land mirror-symmetric.
    points3d = [
        (
            [round(r * radius, 6) for r in xyz[v]]
            if (v := POINT_VERTEX[k]) is not None
            else None
        )
        for k in range(len(points))
    ]
    for a, p in enumerate(points):
        b = next(
            i
            for i, q in enumerate(points)
            if abs(q[0] + p[0]) < 1e-6 and abs(q[1] - p[1]) < 1e-6
        )
        pa, pb = points3d[a], points3d[b]
        if pa is not None and pb is not None:
            assert abs(pa[0] + pb[0]) < 1e-3 and abs(pa[2] - pb[2]) < 1e-3

    config["geometry"]["points3d"] = points3d
    config["geometry"]["fold"] = {
        "sphere": "sphere3v.json",
        "radius_units": round(radius, 4),
        "point_vertex": POINT_VERTEX,
        "faces": "plan_a_faces",
    }

    output = script_dir / "4A-33.json"
    output.write_text(json.dumps(config, indent=2))
    print(f"Generated {output}")
    print(f"Series sizes: {[len(s) for s in triangles]} (total {total})")


if __name__ == "__main__":
    main()
