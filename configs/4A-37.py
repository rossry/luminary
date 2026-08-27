#!/usr/bin/env python3
"""Generate 4A-37.json: 4A-33 with each lower arm extended by two triangles.

Derived from 4A-33.json rather than re-generated, so the relationship is
explicit: everything is identical except the lower arms — series 1
(down-right) and series 3 (down-left) — each continue two strip triangles
beyond their tip (33 -> 37 triangles; series sizes [6,9,3,9,6] ->
[6,11,3,11,6]). The blunted upper arms of 4A-33 are kept: the piece grows
one full lattice step of wingspan per side without gaining height.

The extension continues each arm's triangular lattice exactly the way the
4A-31 -> 4A-35 side-arm extensions did (configs/4A-35.py): two new points
per arm, alternating up/down strip triangles marching along the arm axis —
series 1 along its layer3first direction (16 - 11), series 3 mirrored
along its layer3second direction (21 - 13).
"""

import json
import math
from pathlib import Path

# Per arm: series index, expected current tip triangle, the lattice step
# (a, b) meaning "march by (point a - point b)", and the two existing
# points the new triangles attach to (prev, tip).
ARMS = [
    (1, [27, 24, 28], (16, 11), 27, 28),
    (3, [25, 29, 30], (21, 13), 29, 30),
]

SIDE = 50.0  # arm lattice edge length; every triangle in the family is
# equilateral with this side, so the new tips must be too.

# The fold: net point -> 3V sphere vertex id (configs/sphere3v.json).
# 4A-37 is the plan-A panel set (haircut + hairband 19) unfolded about
# the apex: the pentagon hole is the apex pentagon, the front stub is
# the hairband arc over the door (az 180), and the net's five star
# points (layer2centers) land exactly on the five upper hexagon centers
# where the data/power units mount. Solved by anchored edge propagation
# against the construction app's face sets and validated below; None for
# the two orphaned points (23, 26) that no triangle references.
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
    60,
    75,
    57,
    68,
]


def main() -> None:
    script_dir = Path(__file__).parent
    config = json.loads((script_dir / "4A-33.json").read_text())
    points = config["geometry"]["points"]
    triangles = config["geometry"]["triangles"]

    def check_equilateral(tri: list) -> None:
        for i in range(3):
            p = points[tri[i]]
            q = points[tri[(i + 1) % 3]]
            side = math.dist(p[:2], q[:2])
            assert abs(side - SIDE) < 1e-6, f"non-equilateral extension: {side}"

    for series_idx, tip, (a, b), prev, last in ARMS:
        assert triangles[series_idx][-1] == tip, (
            f"series {series_idx} no longer ends with tip {tip}; "
            "regenerate from a pristine 4A-33.json"
        )
        step_x = points[a][0] - points[b][0]
        step_y = points[a][1] - points[b][1]
        new_1 = len(points)  # prev + step: continues the layer4/layer5 line
        points.append([points[prev][0] + step_x, points[prev][1] + step_y, "navy"])
        new_2 = len(points)  # last + step: the new outermost tip
        points.append([points[last][0] + step_x, points[last][1] + step_y, "silver"])
        # Same up/down alternation the 4A-35 extension used, one lattice
        # step further out: [p, p+u, p+w] then [p+u, p+w, p+u+w].
        for tri in ([prev, new_1, last], [new_1, last, new_2]):
            check_equilateral(tri)
            triangles[series_idx].append(tri)

    sizes = [len(s) for s in triangles]
    assert sizes == [6, 11, 3, 11, 6], f"unexpected series sizes {sizes}"
    total = sum(sizes)
    assert total == 37, f"expected 37 triangles, got {total}"

    # The two arms mirror across the vertical axis; so must the new points.
    for left, right in [(31, 33), (32, 34)]:
        assert abs(points[left][0] + points[right][0]) < 1e-6
        assert abs(points[left][1] - points[right][1]) < 1e-6

    # The new tips extend past 4A-33's viewBox; refit it to the points.
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    pad = 15.0
    x0, y0 = min(xs) - pad, min(ys) - pad
    w, h = max(xs) - x0 + pad, max(ys) - y0 + pad
    config["rendering"]["svg"][
        "viewBox"
    ] = f"{x0:.0f} {y0:.0f} {math.ceil(w):.0f} {math.ceil(h):.0f}"

    # ---- fold onto the 3V sphere ------------------------------------
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

    output = script_dir / "4A-37.json"
    output.write_text(json.dumps(config, indent=2))
    print(f"Generated {output}")
    print(f"Series sizes: {sizes} (total {total}); points: {len(points)}")


if __name__ == "__main__":
    main()
