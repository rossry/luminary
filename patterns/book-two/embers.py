"""Embers: a dying fire with a visible wind. (registration)

The voice lives in :mod:`luminary.patterns.primitives` — points of
light glowing inside an ash-cloud, and a sphere-wide gust that blows
the cloud dark while it fans the coals; every pass consumes some of
them at their brightest. Registered here at a standing gain (no
envelope), so it holds as a scene; nocturne's "dusk" plays the same
voice with the swell-then-drain arc.
"""

from luminary.patterns.primitives import Embers


class EmbersScene(Embers):
    """Registered as ``embers`` with a standing fire (no drain)."""

    notes = (
        "A fire low but alive: coals inside the ash-glow, and a wind you "
        "can see — the cloud darkens under each gust while the sparks "
        "flare hot, and now and then one flares for the last time."
    )

    gain_from = 0.85
    rekindle = True
