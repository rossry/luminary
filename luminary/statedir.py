"""Where runtime state lives — one resolver for every entrypoint.

The runtime state root is ``var/`` (geometry store, pattern uploads,
``var/mapping/``, ``var/mapping-demo/``). The directory itself ships in
the repo (``var/.gitkeep``), so every checkout has it and no existence
or fallback logic is needed anywhere. Both the CLI and the standalone
mapping web entrypoint resolve through this module, so the default
location cannot drift between surfaces. (``store/`` is the dead
pre-rename tree: nothing reads it — delete it, and re-seed demo
geometries with ``luminary.cli seed`` if wanted.)
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
    return Path("var") / sub if sub else Path("var")
