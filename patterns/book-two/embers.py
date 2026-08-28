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
        "A fire low but alive: coals inside the ash banks, and a wind you "
        "can see — each gust beats the cloud down and the damage heals "
        "slowly, while the coals flare and hold their flare, now and then "
        "one for the last time before it rekindles."
    )

    # The scar physics keeps the bed beaten down between gusts; the
    # standing gain compensates so the scene holds its presence.
    gain_from = 1.0
    rekindle = True
