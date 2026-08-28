"""Where runtime state lives — one resolver for every entrypoint.

The runtime state root is the checkout's ``var/`` (geometry documents,
pattern uploads, ``var/audio/``, ``var/mapping/``, ``var/mapping-demo/``,
``var/stage/``). The directory ships in the repo (``var/.gitkeep``), so
every checkout has it and no existence or fallback logic is needed
anywhere. The default is anchored to the repo by ``__file__`` — exactly
like the pattern registry — NOT to the process working directory: a
service unit with no ``WorkingDirectory=`` must not silently read and
populate ``/var`` while the operator's files sit in the checkout. Both
the CLI and the standalone mapping web entrypoint resolve through this
module, so the default location cannot drift between surfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

#: The checkout root: luminary/statedir.py -> luminary/ -> the repo.
_REPO = Path(__file__).resolve().parents[1]


def runtime_state_dir(explicit: Optional[str] = None, sub: str = "") -> Path:
    """Resolve a runtime-state directory: an explicit path is honored
    verbatim; the default is the checkout's ``var/`` (joined with
    ``sub`` for callers whose state lives in a subdirectory),
    independent of the process working directory."""
    if explicit is not None:
        return Path(explicit)
    root = _REPO / "var"
    return root / sub if sub else root
