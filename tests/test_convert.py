"""Vectorized color pipeline (spec §8): round trips and known values."""

import numpy as np

from luminary.color import convert


def test_srgb_roundtrip_all_gray_levels():
    srgb8 = np.stack([np.arange(256)] * 3, axis=1).astype(np.uint8)
    back = convert.linear_to_srgb8(convert.srgb8_to_linear(srgb8))
    np.testing.assert_array_equal(back, srgb8)


def test_oklab_srgb_roundtrip():
    rng = np.random.default_rng(3)
    srgb8 = (rng.random((500, 3)) * 255).astype(np.uint8)
    linear = convert.srgb8_to_linear(srgb8)
    back = convert.oklab_to_linear_srgb(convert.linear_srgb_to_oklab(linear))
    # The published 10-digit matrices are not exact inverses; ~1e-6 residue
    # is far below 8-bit output resolution (1/255 ~ 4e-3 gamma-encoded).
    np.testing.assert_allclose(back, linear, atol=1e-5)


def test_known_values():
    # White: L=1, C~0; primary red: the canonical Ottosson OKLab values.
    white = convert.srgb8_to_oklch(np.array([[255, 255, 255]], dtype=np.uint8))[0]
    assert abs(white[0] - 1.0) < 1e-4 and white[1] < 1e-4
    red = convert.srgb8_to_oklch(np.array([[255, 0, 0]], dtype=np.uint8))[0]
    assert abs(red[0] - 0.6280) < 2e-3
    assert abs(red[1] - 0.2577) < 2e-3
    assert abs(red[2] - 29.23) < 0.5


def test_oklch_oklab_roundtrip_hue_wrap():
    oklch = np.array([[0.5, 0.2, 350.0], [0.5, 0.2, 10.0], [0.7, 0.0, 123.0]])
    back = convert.oklab_to_oklch(convert.oklch_to_oklab(oklch))
    np.testing.assert_allclose(back[:2], oklch[:2], atol=1e-9)
    assert back[2, 1] < 1e-12  # zero chroma preserved (hue undefined)


def test_gamut_clip_preserves_in_gamut_and_fixes_out():
    inside = np.array([[0.5, 0.1, 120.0]])
    clipped = convert.gamut_clip_oklab(convert.oklch_to_oklab(inside))
    np.testing.assert_allclose(clipped, convert.oklch_to_oklab(inside), atol=1e-9)

    wild = np.array([[0.95, 0.4, 260.0], [0.05, 0.4, 120.0], [1.2, 0.2, 0.0]])
    fixed = convert.gamut_clip_oklab(convert.oklch_to_oklab(wild))
    assert np.all(convert.in_gamut(convert.oklab_to_linear_srgb(fixed), eps=1e-3))


def test_oklch_to_srgb8_shape_and_range():
    rng = np.random.default_rng(4)
    oklch = np.stack(
        [rng.random(300), rng.random(300) * 0.4, rng.random(300) * 360], axis=1
    )
    rgb = convert.oklch_to_srgb8(oklch)
    assert rgb.shape == (300, 3) and rgb.dtype == np.uint8
