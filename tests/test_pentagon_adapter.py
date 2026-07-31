"""Pentagon Net adapters (spec §5.5, §7.3): configs stay usable as sources."""

from pathlib import Path

import numpy as np
import pytest

from luminary.geometry.lights import Kind, LightColumns
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

    # The removed tips were the topmost material: the highest remaining
    # light sits strictly lower (SVG y-down: larger min-y = lower).
    top35 = lights35.array[:, LightColumns.Y].min()
    top33 = lights33.array[:, LightColumns.Y].min()
    assert top33 > top35 + 10
