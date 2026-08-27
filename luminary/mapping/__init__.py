"""Deployment mapping: connect the plan to the as-built sphere.

Design: plan/mapping/DESCRIPTION.md. The core here is surface-agnostic:
`plan` derives the panel/board plan from configs, `state` is the pure
interactive state machine, `render` builds the wire/window patterns for
a state snapshot, and `session` ties them to an engine and frame sinks.
Adapters (TUI, serial, WebSocket, the demo page) live around this core
and stay thin.
"""

from luminary.mapping.plan import Plan
from luminary.mapping.state import Event, MappingState, step

__all__ = ["Plan", "Event", "MappingState", "step"]
