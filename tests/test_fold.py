"""The fold onto the 3V sphere: sphere3v generation and 4A-37's 3D columns.

The physical structure is a standard 3V icosahedral geodesic sphere;
4A-37 is the plan-A panel set (37 B-C-C faces) unfolded about the apex
(configs/sphere3v.py, configs/4A-37.py). These tests pin the invariants
the mapping and pattern tooling will rely on.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns, LightsGeometry
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


@pytest.fixture(scope="module")
def sphere():
    return json.loads((CONFIGS / "sphere3v.json").read_text())


@pytest.fixture(scope="module")
def folded():
    return capture(Net.from_json_file(CONFIGS / "4A-37.json"))


def test_sphere3v_regenerates_identically(tmp_path):
    """The generator is deterministic and matches the checked-in file."""
    script = CONFIGS / "sphere3v.py"
    workdir = tmp_path / "configs"
    workdir.mkdir()
    copy = workdir / "sphere3v.py"
    copy.write_text(script.read_text())
    subprocess.run([sys.executable, str(copy)], check=True, capture_output=True)
    assert (workdir / "sphere3v.json").read_text() == (
        CONFIGS / "sphere3v.json"
    ).read_text()


def test_sphere3v_invariants(sphere):
    verts = sphere["vertices"]
    assert len(verts) == 92
    # Unit sphere, apex up, five-fold symmetric ring structure.
    by_ring = {}
    for v in verts:
        assert abs(np.linalg.norm(v["xyz"]) - 1.0) < 1e-9
        by_ring.setdefault(round(v["theta_deg"], 2), []).append(v)
    assert min(by_ring) == 0.0 and max(by_ring) == 180.0
    for theta, ring in by_ring.items():
        assert len(ring) in (1, 5, 10), (theta, len(ring))
    # Every plan-A face is the panel shape: one B strut, two C struts.
    class_of = {}
    for i, j, c in sphere["edges"]:
        class_of[(min(i, j), max(i, j))] = c
    chord = sphere["chord_factors"]
    xyz = {v["id"]: np.array(v["xyz"]) for v in verts}
    for f in sphere["plan_a_faces"]:
        a, b, c = f
        combo = sorted(
            class_of[(min(x, y), max(x, y))] for x, y in [(a, b), (b, c), (a, c)]
        )
        assert combo == ["B", "C", "C"]
        for x, y in [(a, b), (b, c), (a, c)]:
            d = float(np.linalg.norm(xyz[x] - xyz[y]))
            assert abs(d - chord[class_of[(min(x, y), max(x, y))]]) < 1.5e-3
    # The electronics plan: seven 8-channel data units cover 37 panels.
    elec = sphere["electronics"]
    assert len(elec["data_unit_vertices"]) == 7
    assert len(sphere["plan_a_faces"]) == 37


def test_4a37_fold_matches_sphere(sphere):
    """Every net edge maps onto a plan-A dome strut; radius consistent."""
    net = json.loads((CONFIGS / "4A-37.json").read_text())
    g = net["geometry"]
    pv = g["fold"]["point_vertex"]
    radius = g["fold"]["radius_units"]
    xyz = {v["id"]: np.array(v["xyz"]) for v in sphere["vertices"]}
    faces = {tuple(sorted(f)) for f in sphere["plan_a_faces"]}
    for series in g["triangles"]:
        for tri in series:
            mapped = tuple(sorted(pv[i] for i in tri))
            assert mapped in faces, (tri, mapped)
    for i, p3 in enumerate(g["points3d"]):
        if p3 is None:
            assert pv[i] is None
            continue
        assert np.allclose(p3, xyz[pv[i]] * radius, atol=1e-4)


def test_folded_capture_fills_3d(folded):
    a = folded.array
    p3 = a[:, [LightColumns.X3, LightColumns.Y3, LightColumns.Z3]]
    assert np.isfinite(p3).all()
    # Lights lie on flat panels chorded inside the sphere.
    r = np.linalg.norm(p3, axis=1)
    assert 115.0 < float(r.min()) and float(r.max()) < 122.2
    # Polar range: apex pentagon open (no lights above ~17 deg), panels
    # reach below the equator on the arms.
    phi = np.degrees(a[:, LightColumns.PHI_S])
    assert 15.0 < float(phi.min()) < 30.0
    assert 100.0 < float(phi.max()) < 125.0
    # The build frame: the front stub faces -y (the door side); apex +z.
    # Below the arc the front is open — that's the entrance — so no
    # light reaches much beyond the arc's own depth.
    stub = p3[np.abs(a[:, LightColumns.X]) < 20.0]
    assert float(stub[:, 1].min()) < -70.0
    assert float(p3[:, 1].min()) > -80.0
    assert float(p3[:, 2].max()) > 100.0


def test_folded_capture_mirror_symmetry(folded):
    """Net mirror (x -> -x) is the dome mirror (x3 -> -x3)."""
    a = folded.array
    key = np.round(a[:, [LightColumns.X, LightColumns.Y]], 4)
    row_by_pos = {(-k[0], k[1]): i for i, k in enumerate(map(tuple, key))}
    checked = 0
    for i, k in enumerate(map(tuple, key)):
        j = row_by_pos.get(k)
        if j is None:
            continue
        assert abs(a[i, LightColumns.X3] + a[j, LightColumns.X3]) < 1e-3
        assert abs(a[i, LightColumns.Y3] - a[j, LightColumns.Y3]) < 1e-3
        assert abs(a[i, LightColumns.Z3] - a[j, LightColumns.Z3]) < 1e-3
        checked += 1
    assert checked > folded.n * 0.9


def test_folded_doc_round_trips(folded):
    doc = folded.to_file_dict()
    assert doc["space"]["authoritative"] == ["xy", "xyz"]
    back = LightsGeometry.load(doc)
    for col in (LightColumns.X, LightColumns.X3, LightColumns.Z3):
        assert np.allclose(back.array[:, col], folded.array[:, col], equal_nan=True)


def test_flipped_net_orientation():
    """Long arms and the front stub point up (negative y) per the
    construction schematic; short arms point down."""
    net = json.loads((CONFIGS / "4A-37.json").read_text())
    pts = net["geometry"]["points"]
    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]
    # The very top belongs to a long arm ("long arms at the top"); the
    # stub tip is the topmost point on the mirror axis.
    top = min(range(len(pts)), key=lambda i: ys[i])
    assert abs(xs[top]) > 40 and ys[top] < 0
    axis = [i for i in range(len(pts)) if abs(xs[i]) < 1e-6]
    stub_tip = min(axis, key=lambda i: ys[i])
    assert ys[stub_tip] < -70
    # Long arms reach wide, riding the upper half (their zigzag lower
    # vertices may dip a few units past the midline); short arms hold
    # the bottom of the drawing.
    wide = [i for i in range(len(pts)) if abs(xs[i]) > 200]
    assert wide and all(ys[i] < 20 for i in wide)
    assert max(ys) > 100


def test_unfolded_nets_have_no_3d():
    lights = capture(Net.from_json_file(CONFIGS / "4A-33.json"))
    assert lights.space.authoritative == ["xy"]
    assert np.all(lights.array[:, LightColumns.Z3] == 0)
