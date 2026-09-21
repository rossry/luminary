"""Choosing the vibe backend and the models the page offers.

``LUMINARY_VIBE_BACKEND``: ``session`` (a Claude Code session per
prompt, through the Agent SDK — the default whenever the SDK imports and
a ``claude`` CLI is on PATH), or ``api`` (one direct Messages call).
``LUMINARY_VIBE_MODELS``: the comma-separated list the submitter picks
from; the first is the default. ``LUMINARY_VIBE_MODEL`` (single) is
honored as a one-entry list for older configs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

DEFAULT_MODELS = ["claude-sonnet-5", "claude-opus-5"]


def vibe_models() -> List[str]:
    raw = os.environ.get("LUMINARY_VIBE_MODELS") or os.environ.get(
        "LUMINARY_VIBE_MODEL"
    )
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if models:
            return models
    return list(DEFAULT_MODELS)


def default_coder(validator: Optional[Any] = None) -> Tuple[Any, str]:
    """``(coder, backend name)`` per the environment."""
    from luminary.vibe.coder import Coder
    from luminary.vibe.session import SessionCoder, sdk_available

    choice = (os.environ.get("LUMINARY_VIBE_BACKEND") or "auto").strip().lower()
    repo = Path(__file__).resolve().parents[2]
    models = vibe_models()
    if choice == "session" or (choice == "auto" and sdk_available()):
        return SessionCoder(repo, model=models[0], validator=validator), "session"
    return Coder(model=models[0]), "api"
