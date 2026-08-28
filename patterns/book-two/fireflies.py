"""Fireflies: a meadow that learns to flash in unison. (registration)

The voice lives in :mod:`luminary.patterns.repertoire` — importable, so
other shows can nest the meadow. See its docstring for the synchrony
trick: slot offsets lerp toward a metronome by a coherence curve, so
the unison is closed-form, never simulated.
"""

from luminary.patterns import repertoire


class Fireflies(repertoire.Fireflies):
    """Registered as ``fireflies`` with the repertoire tuning."""
