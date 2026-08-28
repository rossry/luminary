"""The stage: the server-side play queue and gapless playback core.

``StageCore`` (``luminary/stage/core.py``) is the ONLY playback decision
logic — one Engine over one geometry, a persisted tracklist, optional
per-entry audio. ``luminary/stage/web.py`` adapts it to HTTP/WS for the
main server; ``luminary/stage/audio.py`` owns the player subprocess.
"""

from luminary.stage.audio import AudioPlayer, detect_player
from luminary.stage.core import QueueEntry, StageCore, StageError

__all__ = [
    "AudioPlayer",
    "detect_player",
    "QueueEntry",
    "StageCore",
    "StageError",
]
