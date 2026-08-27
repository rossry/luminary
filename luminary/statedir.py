"""Where runtime state lives — one resolver for every entrypoint.

The runtime state root is ``var/`` (geometry store, pattern uploads,
``var/mapping/``, ``var/mapping-demo/``). Both the CLI and the
standalone mapping web entrypoint resolve through this module, so the
default location cannot drift between surfaces. There is no legacy
fallback: a checkout still carrying the old ``store/`` name fails fast
with the one-command migration instead of silently starting on an
empty (or stale) tree.
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
    if not Path("var").exists() and Path("store").exists():
        raise SystemExit(
            "runtime state moved from ./store to ./var — run: mv store var"
        )
    return Path("var") / sub if sub else Path("var")
