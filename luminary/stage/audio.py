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

Track lengths: :meth:`AudioPlayer.duration_of` reads a file's exact
runtime (mutagen, falling back to ffprobe), cached by (name, mtime,
size) — the stage uses it to time entries to their tracks. An entry cut
shorter than its track gets a fade-out baked into the player's own
argv at start (:meth:`AudioPlayer.start` with ``cut_at``) for the
players that support a filter (mpv, ffplay); others cut hard.

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
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FADE_S = 2.0  # fade-out length when an entry cuts its track short

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
        self._durations: Dict[Tuple[str, int, int], Optional[float]] = {}
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

    def duration_of(self, filename: str) -> Optional[float]:
        """The file's exact runtime in seconds, or None when it cannot
        be read. mutagen first (pure Python, exact for mp3/flac/ogg/
        wav), ffprobe as fallback; cached by (name, mtime, size)."""
        path = self.resolve(filename)
        if path is None:
            return None
        stat = path.stat()
        key = (filename, stat.st_mtime_ns, stat.st_size)
        if key in self._durations:
            return self._durations[key]
        seconds = self._probe(path)
        self._durations[key] = seconds
        return seconds

    @staticmethod
    def _probe(path: Path) -> Optional[float]:
        try:
            import mutagen

            meta = mutagen.File(path)
            length = getattr(getattr(meta, "info", None), "length", 0.0) or 0.0
            if length > 0:
                return float(length)
        except Exception:
            pass
        if shutil.which("ffprobe"):
            try:
                run = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                seconds = float(run.stdout.strip())
                if seconds > 0:
                    return seconds
            except Exception:
                pass
        return None

    # --------------------------------------------------------------- playback

    @property
    def playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _fade_args(self, cut_at: float) -> List[str]:
        """Player-specific argv for a fade-out ending at ``cut_at``
        (empty when this player has no filter syntax we know)."""
        d = min(_FADE_S, cut_at)
        st = max(cut_at - d, 0.0)
        assert self.command is not None
        player = Path(self.command[0]).name
        if player == "mpv":
            return [f"--af=lavfi=[afade=t=out:st={st:.2f}:d={d:.2f}]"]
        if player == "ffplay":
            return ["-af", f"afade=t=out:st={st:.2f}:d={d:.2f}"]
        return []

    def start(self, filename: str, cut_at: Optional[float] = None) -> bool:
        """Stop whatever is playing and start ``filename``. Returns True
        when a player was actually spawned; a missing player or file is
        logged and the entry simply plays without audio. ``cut_at``
        (seconds) is where the entry will end: when that lands before
        the track does, the player is started with a fade-out ending
        there, so the cut is a breath instead of a chop."""
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
        extra: List[str] = []
        if cut_at is not None and cut_at > 0:
            length = self.duration_of(filename)
            if length is not None and cut_at < length - 0.75:
                extra = self._fade_args(cut_at)
        self._proc = self._spawn(
            self.command + extra + [str(path)],
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
