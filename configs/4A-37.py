#!/usr/bin/env python3
"""Generate 4A-37.json: 4A-35 plus one strip triangle past each upper-arm tip.

Derived from 4A-35.json rather than re-generated, so the relationship is
explicit: everything is identical except each upper arm — series 0
(up-right) and series 4 (up-left) — continues one triangle beyond its tip
(35 -> 37 triangles; series sizes [7,9,3,9,7] -> [8,9,3,9,8]). Equivalently:
4A-33's blunted upper arms extended by two triangles each.

The extension follows the arm's triangular lattice exactly like the 4A-35
side-arm extensions did (configs/4A-35.py "connection triangle"): one new
point per arm, one lattice step beyond layer3, forming an equilateral
triangle on the tip triangle's outer edge.
"""

import json
import math
from pathlib import Path

# Per arm: (series index, new point = 2*a - b, tip triangle it extends,
# new triangle as [edge_pt, new_pt_slot, edge_pt] in lattice order).
# Series 0 marches along its layer3first direction (point 15), series 4
# mirrors along its layer3second direction (point 22), the same first/second
# mirror split the side arms used in 4A-35.
EXTENSIONS = [
    (0, (15, 10), [23, 15, 19], lambda new: [15, new, 23]),
    (4, (22, 14), [26, 18, 22], lambda new: [22, 26, new]),
]

SIDE = 50.0  # arm lattice edge length; every triangle in the family is
# equilateral with this side, so the new tips must be too.


def main() -> None:
    script_dir = Path(__file__).parent
    config = json.loads((script_dir / "4A-35.json").read_text())
    points = config["geometry"]["points"]
    triangles = config["geometry"]["triangles"]

    for series_idx, (a, b), tip, make_triangle in EXTENSIONS:
        assert triangles[series_idx][-1] == tip, (
            f"series {series_idx} no longer ends with tip {tip}; "
            "regenerate from a pristine 4A-35.json"
        )
        new_idx = len(points)
        new_x = 2 * points[a][0] - points[b][0]
        new_y = 2 * points[a][1] - points[b][1]
        points.append([new_x, new_y, "navy"])
        new_triangle = make_triangle(new_idx)
        for i in range(3):
            p = points[new_triangle[i]]
            q = points[new_triangle[(i + 1) % 3]]
            side = math.dist(p[:2], q[:2])
            assert abs(side - SIDE) < 1e-6, f"non-equilateral extension: {side}"
        triangles[series_idx].append(new_triangle)

    sizes = [len(s) for s in triangles]
    assert sizes == [8, 9, 3, 9, 8], f"unexpected series sizes {sizes}"
    total = sum(sizes)
    assert total == 37, f"expected 37 triangles, got {total}"

    # The new tips extend above 4A-35's viewBox; refit it to the points.
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
