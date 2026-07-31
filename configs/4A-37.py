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

    output = script_dir / "4A-37.json"
    output.write_text(json.dumps(config, indent=2))
    print(f"Generated {output}")
    print(f"Series sizes: {sizes} (total {total}); points: {len(points)}")


if __name__ == "__main__":
    main()
