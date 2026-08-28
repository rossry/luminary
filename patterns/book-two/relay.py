"""Relay: bead races on the physical wiring. (registration)

The voice lives in :mod:`luminary.patterns.repertoire` — importable, so
other shows can nest a heat or three. See its docstring: every strip is
a lane, racers run the serpentine in index order, and the winner's lane
floods gold at the line.
"""

from luminary.patterns import repertoire


class Relay(repertoire.Relay):
    """Registered as ``relay`` with the repertoire tuning."""
