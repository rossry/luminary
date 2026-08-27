"""Pentagon Net adapters (spec §5.5, §7.3): configs stay usable as sources."""

from pathlib import Path

import numpy as np
import pytest

from luminary.geometry.lights import MAX_CHANNELS, Kind, LightColumns
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture, to_scaffold

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "3A-33.json"


@pytest.fixture(scope="module")
def net():
    return Net.from_json_file(CONFIG)


def test_to_scaffold_lines(net):
    scaffold = to_scaffold(net)
    assert scaffold.n_lines == len(net.config.geometry.lines)
    # Planar, derived normals, chord midpoints.
    assert np.allclose(scaffold.normals[:, :, 2], 0.0)
    assert np.allclose(np.linalg.norm(scaffold.normals, axis=2), 1.0, atol=1e-9)


def test_capture_one_light_per_beam_with_display(net):
    lights = capture(net)
    n_beams = sum(
        len(edge)
        for tri in net.triangles
        for facet in tri.get_facets()
        for edge in facet.get_beams()
    )
    assert lights.n == n_beams
    assert np.all(lights.array[:, LightColumns.KIND] == Kind.ACTIVE)
    # Every light carries its beam polygon as a display shape (spec §6.5.3).
    assert all(shape is not None and len(shape) >= 3 for shape in lights.display)
    # Directions are unit in-plane vectors; extents lie forward of positions.
    d = lights.array[:, [LightColumns.DX, LightColumns.DY]]
    assert np.allclose(np.linalg.norm(d, axis=1), 1.0, atol=1e-6)
    reach = np.einsum(
        "ij,ij->i",
        lights.array[:, [LightColumns.EX, LightColumns.EY]]
        - lights.array[:, [LightColumns.X, LightColumns.Y]],
        d,
    )
    assert np.all(reach > -1e-6)


@pytest.mark.parametrize("name", ["3A-33", "4A-33", "4A-37"])
def test_beam_throw_points_into_its_own_facet(name):
    """Every LED throws toward the interior of the facet it lights.

    The physical claim: each strip is mounted on a facet's own boundary --
    a PVC pipe or a frame strut -- and emits across *that* facet, never out
    through the frame into the gap between panels, and never across a pipe
    into its neighbour. On a shared interior pipe the two facets carry two
    rows back to back.

    This is not decoration. ``Beam.forward_vector`` (geometry/beam.py) takes
    the counterclockwise perpendicular and documents it as "pointing into
    facet interior", which only holds for counterclockwise-wound facets;
    most of these nets are wound the other way. Without the correction in
    ``capture()`` this assertion passes for 6% of 4A-33's lights. The nets
    are parameterized because they carry different winding mixes (3A-33 is
    19 clockwise of 33 triangles, 4A-33 is 31 of 33), so a fix that
    hardcodes one winding still fails here.
    """
    net = Net.from_json_file(CONFIG.parent / f"{name}.json")
    lights = capture(net)
    a = lights.array
    row_of = {
        (
            int(a[i, LightColumns.CONTROLLER]),
            int(a[i, LightColumns.CHANNEL]),
            int(a[i, LightColumns.INDEX]),
        ): i
        for i in range(lights.n)
    }

    # Replay capture()'s identity assignment: from_specs sorts rows into
    # canonical (controller, channel, index) order, so append order is not
    # row order and the beams have to be paired back by identity.
    next_index = {ch: 0 for ch in range(MAX_CHANNELS)}
    facet_ordinal = 0
    checked = 0
    for triangle in net.triangles:
        for facet in triangle.get_facets():
            channel = facet_ordinal % MAX_CHANNELS
            facet_ordinal += 1
            verts = facet.vertices
            cx = sum(v.x for v in verts) / len(verts)
            cy = sum(v.y for v in verts) / len(verts)
            for edge_beams in facet.get_beams():
                for _beam in edge_beams:
                    i = row_of[(0, channel, next_index[channel])]
                    next_index[channel] += 1
                    px, py = a[i, LightColumns.X], a[i, LightColumns.Y]
                    dx, dy = a[i, LightColumns.DX], a[i, LightColumns.DY]
                    if not (np.isfinite(dx) and np.isfinite(dy)):
                        continue  # degenerate beam: capture() emits no dir
                    assert (cx - px) * dx + (cy - py) * dy > 0, (
                        f"{name} light {i} (channel {channel}, index "
                        f"{next_index[channel] - 1}) throws away from the "
                        f"centroid of the facet it lights"
                    )
                    checked += 1
    assert checked == lights.n


def test_capture_identity_is_valid_and_dense(net):
    lights = capture(net, channels=8)
    channels = lights.ints(LightColumns.CHANNEL)
    assert channels.min() >= 0 and channels.max() < 8
    for ch in range(8):
        indices = np.sort(lights.ints(LightColumns.INDEX)[channels == ch])
        assert np.array_equal(indices, np.arange(indices.size))


def test_4a33_is_4a35_minus_upper_arm_tips():
    """configs/4A-33: same net as 4A-35 with the two upper-arm tip
    triangles removed (see configs/4A-33.py)."""
    net35 = Net.from_json_file(CONFIG.parent / "4A-35.json")
    net33 = Net.from_json_file(CONFIG.parent / "4A-33.json")
    assert len(net35.triangles) == 35 and len(net33.triangles) == 33

    lights35, lights33 = capture(net35), capture(net33)
    per_triangle = lights35.n // 35
    assert lights33.n == lights35.n - 2 * per_triangle

    # The removed tips are the extreme material of the short arms — which
    # point DOWN in the flipped net frame (long arms up, per the
    # construction schematic): the lowest remaining light sits strictly
    # higher (SVG y-down: smaller max-y = higher).
    bottom35 = lights35.array[:, LightColumns.Y].max()
    bottom33 = lights33.array[:, LightColumns.Y].max()
    assert bottom33 < bottom35 - 10


def test_4a37_is_4a33_plus_lower_arm_extensions():
    """configs/4A-37: same net as 4A-33 with each lower arm extended by
    two strip triangles (see configs/4A-37.py). Series [6,11,3,11,6]."""
    import json

    doc = json.loads((CONFIG.parent / "4A-37.json").read_text())
    assert [len(s) for s in doc["geometry"]["triangles"]] == [6, 11, 3, 11, 6]

    net33 = Net.from_json_file(CONFIG.parent / "4A-33.json")
    net37 = Net.from_json_file(CONFIG.parent / "4A-37.json")
    assert len(net33.triangles) == 33 and len(net37.triangles) == 37

    lights33, lights37 = capture(net33), capture(net37)
    per_triangle = lights33.n // 33
    assert lights37.n == lights33.n + 4 * per_triangle

    # The extensions ride the long arms outward without rising above
    # them; the growth is pure wingspan (one lattice step per side).
    top33 = lights33.array[:, LightColumns.Y].min()
    top37 = lights37.array[:, LightColumns.Y].min()
    assert abs(top37 - top33) < 1e-9
    xs33 = lights33.array[:, LightColumns.X]
    xs37 = lights37.array[:, LightColumns.X]
    assert xs37.max() > xs33.max() + 40
    assert xs37.min() < xs33.min() - 40
