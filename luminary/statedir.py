"""Where runtime state lives — one resolver for every entrypoint.

The runtime state root is ``var/`` (geometry store, pattern uploads,
``var/mapping/``, ``var/mapping-demo/``); a legacy ``store/`` tree keeps
working with a rename nudge until it is moved (``mv store var``). Both
the CLI and the standalone mapping web entrypoint resolve through this
module, so the default location cannot drift between surfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def runtime_state_dir(explicit: Optional[str] = None, sub: str = "") -> Path:
    """Resolve a runtime-state directory: an explicit path is honored
    verbatim; the default is ``var/`` (joined with ``sub`` for callers
    whose state lives in a subdirectory)."""
    if explicit is not None:
        return Path(explicit)
    root = Path("var")
    if not root.exists() and Path("store").exists():
        print("note: using legacy ./store; rename it: mv store var")
        root = Path("store")
    return root / sub if sub else root
