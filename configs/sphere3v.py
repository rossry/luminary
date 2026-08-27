#!/usr/bin/env python3
"""Generate sphere3v.json: the canonical 3V geodesic sphere of the build.

The physical structure is a standard 3V icosahedral geodesic sphere
(Class I, Method 1): an icosahedron, apex up, each face trisected flat
and projected to the sphere — 92 vertices (12 + 60 + 20, counting the
never-built nadir), 270 struts in three classes (A/B/C = the red/blue/
yellow tube lengths). Vertex NUMBERING follows the construction app
("sphere.html", BUILD 20260817-halo — the site's construction reference):
its vertex table is embedded below as the identity authority, each id
matched to the first-principles vertex it names and asserted to agree.
Coordinates in the output are the EXACT values, not the app's rounded
table.

Frame: +z is up (apex), the door/front is azimuth 180 deg, and screen-
right in the schematics is azimuth > 180 (the app's own convention).
The output also carries the electronics plan extracted from the app:
panel faces of plan-A (haircut + hairband 19 = 37 BCC faces), the seven
data-unit vertices (8-channel controllers), power-unit sites, and the
base-station vertex.
"""

import json
import math
from pathlib import Path

# Vertex identity authority: (polar theta deg, azimuth rad) per id, from
# the construction app. Id 91 is the phantom nadir (never built).
APP_TABLE = [
    (0, 0),
    (20.08, 0),
    (20.08, 1.25664),
    (20.08, 2.51327),
    (20.08, -2.51327),
    (20.08, -1.25664),
    (37.38, 0.62832),
    (37.38, 1.88496),
    (37.38, -3.14159),
    (37.38, -1.88496),
    (37.38, -0.62832),
    (43.36, 0),
    (43.36, 1.25664),
    (43.36, 2.51327),
    (43.36, -2.51327),
    (43.36, -1.25664),
    (59.01, 0.39071),
    (59.01, -0.39071),
    (59.01, 1.64735),
    (59.01, 0.86593),
    (59.01, 2.90399),
    (59.01, 2.12256),
    (59.01, -2.12256),
    (59.01, -2.90399),
    (59.01, -0.86592),
    (59.01, -1.64735),
    (63.43, 0),
    (63.43, 1.25664),
    (63.43, 2.51327),
    (63.43, -2.51327),
    (63.43, -1.25664),
    (79.19, 0.62832),
    (79.19, 1.88496),
    (79.19, -3.14159),
    (79.19, -1.88496),
    (79.19, -0.62832),
    (80.12, 0.20627),
    (80.12, -0.20627),
    (80.12, 1.46291),
    (80.12, 1.05036),
    (80.12, 2.71955),
    (80.12, 2.307),
    (80.12, -2.307),
    (80.12, -2.71955),
    (80.12, -1.05036),
    (80.12, -1.46291),
    (99.88, 0.42205),
    (99.88, -0.42205),
    (99.88, 1.67868),
    (99.88, 0.83459),
    (99.88, 2.93532),
    (99.88, 2.09123),
    (99.88, -2.09123),
    (99.88, -2.93532),
    (99.88, -0.83459),
    (99.88, -1.67868),
    (100.81, 0),
    (100.81, 1.25664),
    (100.81, 2.51327),
    (100.81, -2.51327),
    (100.81, -1.25664),
    (116.57, 0.62832),
    (116.57, 1.88496),
    (116.57, 3.14159),
    (116.57, -1.88496),
    (116.57, -0.62832),
    (120.99, 0.23761),
    (120.99, -0.23761),
    (120.99, 1.49424),
    (120.99, 1.01903),
    (120.99, 2.75088),
    (120.99, 2.27567),
    (120.99, -2.27567),
    (120.99, -2.75088),
    (120.99, -1.01903),
    (120.99, -1.49424),
    (136.64, 0.62832),
    (136.64, 1.88496),
    (136.64, -3.14159),
    (136.64, -1.88496),
    (136.64, -0.62832),
    (142.62, 0),
    (142.62, 1.25664),
    (142.62, 2.51327),
    (142.62, -2.51327),
    (142.62, -1.25664),
    (159.92, 0.62832),
    (159.92, 1.88496),
    (159.92, -3.14159),
    (159.92, -1.88496),
    (159.92, -0.62832),
    (180, -3.14159),
]

# Strut list with length classes (A/B/C), app vertex ids.
EDGES = [
    (0, 1, "A"),
    (0, 2, "A"),
    (0, 3, "A"),
    (0, 4, "A"),
    (0, 5, "A"),
    (1, 2, "B"),
    (1, 5, "B"),
    (1, 6, "C"),
    (1, 10, "C"),
    (1, 11, "B"),
    (2, 3, "B"),
    (2, 6, "C"),
    (2, 7, "C"),
    (2, 12, "B"),
    (3, 4, "B"),
    (3, 7, "C"),
    (3, 8, "C"),
    (3, 13, "B"),
    (4, 5, "B"),
    (4, 8, "C"),
    (4, 9, "C"),
    (4, 14, "B"),
    (5, 9, "C"),
    (5, 10, "C"),
    (5, 15, "B"),
    (6, 11, "C"),
    (6, 12, "C"),
    (6, 16, "C"),
    (6, 19, "C"),
    (7, 12, "C"),
    (7, 13, "C"),
    (7, 18, "C"),
    (7, 21, "C"),
    (8, 13, "C"),
    (8, 14, "C"),
    (8, 20, "C"),
    (8, 23, "C"),
    (9, 14, "C"),
    (9, 15, "C"),
    (9, 22, "C"),
    (9, 25, "C"),
    (10, 11, "C"),
    (10, 15, "C"),
    (10, 17, "C"),
    (10, 24, "C"),
    (11, 16, "B"),
    (11, 17, "B"),
    (11, 26, "A"),
    (12, 18, "B"),
    (12, 19, "B"),
    (12, 27, "A"),
    (13, 20, "B"),
    (13, 21, "B"),
    (13, 28, "A"),
    (14, 22, "B"),
    (14, 23, "B"),
    (14, 29, "A"),
    (15, 24, "B"),
    (15, 25, "B"),
    (15, 30, "A"),
    (16, 19, "B"),
    (16, 26, "A"),
    (16, 31, "C"),
    (16, 36, "B"),
    (17, 24, "B"),
    (17, 26, "A"),
    (17, 35, "C"),
    (17, 37, "B"),
    (18, 21, "B"),
    (18, 27, "A"),
    (18, 32, "C"),
    (18, 38, "B"),
    (19, 27, "A"),
    (19, 31, "C"),
    (19, 39, "B"),
    (20, 23, "B"),
    (20, 28, "A"),
    (20, 33, "C"),
    (20, 40, "B"),
    (21, 28, "A"),
    (21, 32, "C"),
    (21, 41, "B"),
    (22, 25, "B"),
    (22, 29, "A"),
    (22, 34, "C"),
    (22, 42, "B"),
    (23, 29, "A"),
    (23, 33, "C"),
    (23, 43, "B"),
    (24, 30, "A"),
    (24, 35, "C"),
    (24, 44, "B"),
    (25, 30, "A"),
    (25, 34, "C"),
    (25, 45, "B"),
    (26, 36, "A"),
    (26, 37, "A"),
    (27, 38, "A"),
    (27, 39, "A"),
    (28, 40, "A"),
    (28, 41, "A"),
    (29, 42, "A"),
    (29, 43, "A"),
    (30, 44, "A"),
    (30, 45, "A"),
    (31, 36, "C"),
    (31, 39, "C"),
    (31, 46, "C"),
    (31, 49, "C"),
    (32, 38, "C"),
    (32, 41, "C"),
    (32, 48, "C"),
    (32, 51, "C"),
    (33, 40, "C"),
    (33, 43, "C"),
    (33, 50, "C"),
    (33, 53, "C"),
    (34, 42, "C"),
    (34, 45, "C"),
    (34, 52, "C"),
    (34, 55, "C"),
    (35, 37, "C"),
    (35, 44, "C"),
    (35, 47, "C"),
    (35, 54, "C"),
    (36, 37, "B"),
    (36, 46, "B"),
    (36, 56, "C"),
    (37, 47, "B"),
    (37, 56, "C"),
    (38, 39, "B"),
    (38, 48, "B"),
    (38, 57, "C"),
    (39, 49, "B"),
    (39, 57, "C"),
    (40, 41, "B"),
    (40, 50, "B"),
    (40, 58, "C"),
    (41, 51, "B"),
    (41, 58, "C"),
    (42, 43, "B"),
    (42, 52, "B"),
    (42, 59, "C"),
    (43, 53, "B"),
    (43, 59, "C"),
    (44, 45, "B"),
    (44, 54, "B"),
    (44, 60, "C"),
    (45, 55, "B"),
    (45, 60, "C"),
    (46, 49, "B"),
    (46, 56, "C"),
    (46, 61, "A"),
    (46, 66, "B"),
    (47, 54, "B"),
    (47, 56, "C"),
    (47, 65, "A"),
    (47, 67, "B"),
    (48, 51, "B"),
    (48, 57, "C"),
    (48, 62, "A"),
    (48, 68, "B"),
    (49, 57, "C"),
    (49, 61, "A"),
    (49, 69, "B"),
    (50, 53, "B"),
    (50, 58, "C"),
    (50, 63, "A"),
    (50, 70, "B"),
    (51, 58, "C"),
    (51, 62, "A"),
    (51, 71, "B"),
    (52, 55, "B"),
    (52, 59, "C"),
    (52, 64, "A"),
    (52, 72, "B"),
    (53, 59, "C"),
    (53, 63, "A"),
    (53, 73, "B"),
    (54, 60, "C"),
    (54, 65, "A"),
    (54, 74, "B"),
    (55, 60, "C"),
    (55, 64, "A"),
    (55, 75, "B"),
    (56, 66, "C"),
    (56, 67, "C"),
    (57, 68, "C"),
    (57, 69, "C"),
    (58, 70, "C"),
    (58, 71, "C"),
    (59, 72, "C"),
    (59, 73, "C"),
    (60, 74, "C"),
    (60, 75, "C"),
    (61, 66, "A"),
    (61, 69, "A"),
    (61, 76, "A"),
    (62, 68, "A"),
    (62, 71, "A"),
    (62, 77, "A"),
    (63, 70, "A"),
    (63, 73, "A"),
    (63, 78, "A"),
    (64, 72, "A"),
    (64, 75, "A"),
    (64, 79, "A"),
    (65, 67, "A"),
    (65, 74, "A"),
    (65, 80, "A"),
    (66, 67, "B"),
    (66, 76, "B"),
    (66, 81, "C"),
    (67, 80, "B"),
    (67, 81, "C"),
    (68, 69, "B"),
    (68, 77, "B"),
    (68, 82, "C"),
    (69, 76, "B"),
    (69, 82, "C"),
    (70, 71, "B"),
    (70, 78, "B"),
    (70, 83, "C"),
    (71, 77, "B"),
    (71, 83, "C"),
    (72, 73, "B"),
    (72, 79, "B"),
    (72, 84, "C"),
    (73, 78, "B"),
    (73, 84, "C"),
    (74, 75, "B"),
    (74, 80, "B"),
    (74, 85, "C"),
    (75, 79, "B"),
    (75, 85, "C"),
    (76, 81, "C"),
    (76, 82, "C"),
    (76, 86, "B"),
    (77, 82, "C"),
    (77, 83, "C"),
    (77, 87, "B"),
    (78, 83, "C"),
    (78, 84, "C"),
    (78, 88, "B"),
    (79, 84, "C"),
    (79, 85, "C"),
    (79, 89, "B"),
    (80, 81, "C"),
    (80, 85, "C"),
    (80, 90, "B"),
    (81, 86, "C"),
    (81, 90, "C"),
    (82, 86, "C"),
    (82, 87, "C"),
    (83, 87, "C"),
    (83, 88, "C"),
    (84, 88, "C"),
    (84, 89, "C"),
    (85, 89, "C"),
    (85, 90, "C"),
    (86, 87, "B"),
    (86, 90, "B"),
    (87, 88, "B"),
    (88, 89, "B"),
    (89, 90, "B"),
]

# Plan-A panel faces: haircut + hairband 19 (2026 design, 37 panels).
PLAN_A_FACES = [
    (1, 2, 6),
    (1, 5, 10),
    (1, 6, 11),
    (1, 10, 11),
    (2, 3, 7),
    (2, 6, 12),
    (2, 7, 12),
    (3, 4, 8),
    (3, 7, 13),
    (3, 8, 13),
    (4, 5, 9),
    (4, 8, 14),
    (4, 9, 14),
    (5, 9, 15),
    (5, 10, 15),
    (6, 11, 16),
    (6, 12, 19),
    (6, 16, 19),
    (7, 12, 18),
    (7, 13, 21),
    (7, 18, 21),
    (9, 14, 22),
    (9, 15, 25),
    (9, 22, 25),
    (10, 11, 17),
    (10, 15, 24),
    (10, 17, 24),
    (18, 21, 32),
    (18, 32, 38),
    (22, 25, 34),
    (25, 34, 45),
    (32, 38, 48),
    (34, 45, 55),
    (38, 48, 57),
    (45, 55, 60),
    (48, 57, 68),
    (55, 60, 75),
]

# Electronics (from the app's cable plan, top frame):
DATA_UNIT_VERTICES = [6, 7, 8, 9, 10, 38, 45]  # 8-channel controllers
DATA_CONSOLIDATIONS = {38: [57, 32], 45: [60, 34]}  # chip serves hex pair
POWER_UNIT_VERTICES = [6, 7, 8, 9, 10, 32, 34, 57, 60]
POWER_DOUBLE_UNITS = [6, 7, 9, 10]  # borders >= 4 panels -> two units
BASE_STATION_VERTEX = 81  # back, theta 142.62

# Exact 3V chord factors (chord / sphere radius) per strut class.
CHORD = {"A": 0.34862, "B": 0.40355, "C": 0.41241}


def exact_3v_vertices():
    """All 92 vertices of the 3V sphere by trisect-and-project."""
    top = (0.0, 0.0, 1.0)
    upper = [
        (
            (2 / math.sqrt(5)) * math.cos(math.radians(72 * k)),
            (2 / math.sqrt(5)) * math.sin(math.radians(72 * k)),
            1 / math.sqrt(5),
        )
        for k in range(5)
    ]
    lower = [
        (
            (2 / math.sqrt(5)) * math.cos(math.radians(36 + 72 * k)),
            (2 / math.sqrt(5)) * math.sin(math.radians(36 + 72 * k)),
            -1 / math.sqrt(5),
        )
        for k in range(5)
    ]
    bottom = (0.0, 0.0, -1.0)
    ico = [top] + upper + lower + [bottom]
    faces = []
    for k in range(5):
        u0, u1 = 1 + k, 1 + (k + 1) % 5
        l0, l1 = 6 + k, 6 + (k + 1) % 5
        faces += [(0, u0, u1), (u0, l0, u1), (u1, l0, l1), (11, l1, l0)]
    seen = {}
    for a, b, c in faces:
        pa, pb, pc = ico[a], ico[b], ico[c]
        for i in range(4):
            for j in range(4 - i):
                k = 3 - i - j
                p = tuple((i * pa[d] + j * pb[d] + k * pc[d]) / 3.0 for d in range(3))
                n = math.sqrt(sum(v * v for v in p))
                p = tuple(v / n for v in p)
                seen[tuple(round(v, 9) for v in p)] = p
    return list(seen.values())


def main() -> None:
    exact = exact_3v_vertices()
    assert len(exact) == 92, f"expected 92 vertices, got {len(exact)}"

    matched = []
    used = set()
    for vid, (theta_deg, az_rad) in enumerate(APP_TABLE):
        th = math.radians(theta_deg)
        ref = (
            math.sin(th) * math.cos(az_rad),
            math.sin(th) * math.sin(az_rad),
            math.cos(th),
        )
        best, best_dot = None, -2.0
        for i, p in enumerate(exact):
            d = sum(a * b for a, b in zip(ref, p))
            if d > best_dot:
                best, best_dot = i, d
        err_deg = math.degrees(math.acos(max(-1.0, min(1.0, best_dot))))
        assert err_deg < 0.05, f"vertex {vid}: {err_deg:.4f} deg from exact"
        assert best not in used, f"vertex {vid}: exact vertex reused"
        used.add(best)
        matched.append(exact[best])

    # Every strut's exact chord must match its class length.
    for i, j, c in EDGES:
        chord = math.dist(matched[i], matched[j])
        assert abs(chord - CHORD[c]) < 1.5e-3, (i, j, c, chord)

    # Every plan-A face must be a B-C-C triangle (the panel shape).
    class_of = {}
    for i, j, c in EDGES:
        class_of[(min(i, j), max(i, j))] = c
    for f in PLAN_A_FACES:
        a, b, c = f
        combo = sorted(
            class_of[(min(x, y), max(x, y))] for x, y in [(a, b), (b, c), (a, c)]
        )
        assert combo == ["B", "C", "C"], (f, combo)

    vertices = []
    for vid, p in enumerate(matched):
        theta = math.degrees(math.acos(max(-1.0, min(1.0, p[2]))))
        az = math.degrees(math.atan2(p[1], p[0])) % 360.0
        # Build frame: apex +z, door/front at -y, screen-right +x — a
        # 90-degree rotation of the raw (az-0 = +x) construction frame.
        build = (-p[1], p[0], p[2])
        vertices.append(
            {
                "id": vid,
                "theta_deg": round(theta, 6),
                "az_deg": round(az, 6),
                "xyz": [round(v, 9) for v in build],
            }
        )

    # ---- data-aux (construction app, aux mode "data") ----------------
    # The front hexagon unit (az 180, over the door) keeps its power unit
    # and primary, but its three hairband panels hand their DATA role to
    # the flanking hexagon units over chained secondaries. Screen right
    # (az > 180) carries two of the three — its flank face plus the
    # middle face over the door — the left side carries one. Derived
    # here from the faces alone and asserted against the app's values.
    nbr: dict = {}
    for i, j, _c in EDGES:
        nbr.setdefault(i, set()).add(j)
        nbr.setdefault(j, set()).add(i)

    def off_front(v: int) -> float:
        return (vertices[v]["az_deg"] - 180.0 + 180.0) % 360.0 - 180.0

    hexes = [u for u in DATA_UNIT_VERTICES if u not in DATA_CONSOLIDATIONS]
    front = min(hexes, key=lambda u: abs(off_front(u)))
    assert front == 8 and abs(off_front(front)) < 1e-6, front
    front_faces = [f for f in PLAN_A_FACES if front in f]
    assert len(front_faces) == 3, front_faces
    others = [v for f in front_faces for v in f if v != front]
    shared = sorted(v for v in set(others) if others.count(v) == 2)
    (middle,) = [f for f in front_faces if all(v in f for v in shared)]
    right = max(shared, key=off_front)  # screen right: az > 180
    unit_at = {s: next(u for u in hexes if u != front and s in nbr[u]) for s in shared}

    def flank_of(face: tuple) -> int:
        if face is middle:  # the middle face rides the right secondary
            return right
        (s,) = [v for v in shared if v in face]
        return s

    reassign = sorted(
        (tuple(sorted(face)), unit_at[flank_of(face)]) for face in front_faces
    )
    assert reassign == [((3, 4, 8), 9), ((3, 8, 13), 7), ((4, 8, 14), 9)], reassign

    out = {
        "schema": "luminary.sphere3v/1",
        "source": (
            "standard 3V icosahedral geodesic sphere (Class I, Method 1); "
            "vertex ids per the construction app sphere.html, "
            "BUILD 20260817-halo"
        ),
        "frame": {
            "up": "+z (apex)",
            "front": "-y (the door faces -y; az_deg 180)",
            "screen_right": "+x (az_deg > 180)",
            "note": "az_deg is the construction app's azimuth; xyz is "
            "the build frame (a 90-degree rotation of the app's frame)",
        },
        "chord_factors": CHORD,
        "vertices": vertices,
        "edges": [[i, j, c] for i, j, c in EDGES],
        "plan_a_faces": [list(f) for f in PLAN_A_FACES],
        "electronics": {
            "data_unit_vertices": DATA_UNIT_VERTICES,
            "data_consolidations": {str(k): v for k, v in DATA_CONSOLIDATIONS.items()},
            "power_unit_vertices": POWER_UNIT_VERTICES,
            "power_double_units": POWER_DOUBLE_UNITS,
            "base_station_vertex": BASE_STATION_VERTEX,
            "data_aux": {
                "unit": front,
                "reassign": [[list(face), unit] for face, unit in reassign],
                "note": (
                    "aux mode 'data': the front unit keeps its power unit "
                    "and primary, but its panels' data rides the flanking "
                    "hexes (screen right takes the middle + right faces)"
                ),
            },
        },
    }
    output = Path(__file__).parent / "sphere3v.json"
    output.write_text(json.dumps(out, indent=1))
    print(f"Generated {output}")
    print(
        f"vertices: {len(vertices)}; edges: {len(EDGES)}; plan-A faces: {len(PLAN_A_FACES)}"
    )


if __name__ == "__main__":
    main()
