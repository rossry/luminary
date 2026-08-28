"""Optional synchronized audio for stage entries.

One player subprocess at a time, started when an entry with an ``audio``
file begins and terminated on skip/advance — no analysis, no seeking; the
synchronization contract is simply "the player starts at the entry's
t=0", the same origin the entry's pattern receives.

The player command is auto-detected at startup (first of mpv, cvlc,
ffplay on PATH; ``serve --audio-player CMD`` overrides). With no player
present the stage still runs — entries play their patterns and audio is
disabled, logged once here. Files live in ``<state dir>/audio/``; entry
audio references are bare filenames inside that directory only (no path
separators), so the queue can never reach outside it.

``spawn`` is injectable (tests substitute a fake ``Popen``) — never
spawn a real player in tests.
"""

from __future__ import annotations

import contextlib
import logging
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# Auto-detection order: every candidate plays one file from argv and
# exits by itself when it ends (so "audio finished" is just process exit).
_PLAYERS = [
    ["mpv", "--no-video"],
    ["cvlc", "--play-and-exit", "--intf", "dummy"],
    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"],
]

_STOP_TIMEOUT = 2.0  # seconds to wait after terminate() before kill()


def detect_player(override: Optional[str] = None) -> Optional[List[str]]:
    """The audio player command, as argv. An explicit ``override`` is
    honored verbatim (shlex-split); otherwise the first candidate whose
    binary is on PATH wins; None means audio is disabled."""
    if override:
        return shlex.split(override)
    for command in _PLAYERS:
        if shutil.which(command[0]):
            return list(command)
    return None


class AudioPlayer:
    """Owns at most one player subprocess for the stage.

    ``command`` is the player argv (from :func:`detect_player`) or None
    for disabled audio; the file path is appended per play. ``spawn``
    defaults to ``subprocess.Popen`` and exists to be replaced in tests.
    """

    def __init__(
        self,
        command: Optional[List[str]],
        audio_dir: Path,
        spawn: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.command = list(command) if command else None
        self.audio_dir = Path(audio_dir)
        self._spawn = spawn
        self._proc: Optional[Any] = None
        if self.command is None:
            logger.info(
                "stage audio disabled: no player found (looked for mpv, cvlc, "
                "ffplay) — `sudo apt install mpv`, or pass --audio-player"
            )

    # -------------------------------------------------------------- inventory

    @property
    def player_name(self) -> Optional[str]:
        """The detected command as one string, for status APIs."""
        return " ".join(self.command) if self.command else None

    def resolve(self, filename: str) -> Optional[Path]:
        """The file's path inside the audio directory, or None if the
        name reaches outside it (any path separators) or doesn't exist."""
        if not filename or Path(filename).name != filename:
            return None
        path = self.audio_dir / filename
        return path if path.is_file() else None

    def has(self, filename: str) -> bool:
        return self.resolve(filename) is not None

    def list_files(self) -> List[str]:
        """Playable filenames (every regular non-hidden file), sorted."""
        if not self.audio_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in self.audio_dir.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )

    # --------------------------------------------------------------- playback

    @property
    def playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, filename: str) -> bool:
        """Stop whatever is playing and start ``filename``. Returns True
        when a player was actually spawned; a missing player or file is
        logged and the entry simply plays without audio."""
        self.stop()
        path = self.resolve(filename)
        if path is None:
            logger.warning(
                "stage audio: %r is not a file in %s — entry plays silent",
                filename,
                self.audio_dir,
            )
            return False
        if self.command is None:
            return False  # disabled (already logged once at startup)
        self._proc = self._spawn(
            self.command + [str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def stop(self) -> None:
        """Terminate the current player, escalating to kill; idempotent."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        with contextlib.suppress(Exception):
            proc.terminate()
            try:
                proc.wait(timeout=_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=_STOP_TIMEOUT)
