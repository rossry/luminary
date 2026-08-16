"""Pentagon Net adapters: the 2.0 geometry as a scaffold/lights source (§5.5, §7.3).

The pentagon Net (Triangles -> Facets -> Beams) is demoted from core runtime
concept to *constructor*: ``to_scaffold`` emits its lines as a scaffold, and
``capture`` emits one light per beam — with the beam polygon preserved as the
light's display shape (spec §6.5.3, review §19.5). The Net/Triangle/Facet/Beam
classes themselves remain in ``luminary.geometry`` for the SVG diagram and
this adapter; nothing per-frame touches them.
"""

from luminary.geometry.pentagon.adapters import capture, to_scaffold

__all__ = ["capture", "to_scaffold"]
