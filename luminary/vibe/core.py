"""VibeCore: the shared state of a vibe session — every page sees the same.

Vibe mode is prompt-to-pattern on the stage: someone types a prompt, a
coding model writes a pattern, the server validates it, saves it as
generation #N, and hot-cuts the stage to it — the sphere and every open
page switch together. The thread of generations, the queue of prompts
still cooking, and which pattern is showing all live HERE, on the
server; the page is a thin adapter that polls this and sends verbs
(implementation-notes §2.9). Open it in five places and they agree.

What a prompt carries: the text, who typed it, an optional name, the
model they chose, and — captured at the moment they pressed enter, not
when the worker gets to it — the pattern that was showing and its
source. "Slower and more purple" means that one, even if someone cut to
something else while the model was busy.

Everything is kept. Each generation is a file under ``<state>/vibe/``,
``vibe-0001.py`` onward, never overwritten: a draft the validator
rejected is preserved beside it under a leading underscore (the registry
skips those), and ``log.json`` holds the whole thread. The directory is
a registry volume, so every generation is a real pattern — queueable
from the stage page, promotable into ``patterns/`` by copying the file.
"""

from __future__ import annotations

import ast
import json
import logging
import queue
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

from luminary.patterns.registry import PatternRegistry
from luminary.stage.core import StageCore, StageError

logger = logging.getLogger(__name__)

#: A generation's registry name: the number is its identity.
PATTERN_PREFIX = "vibe-"
FRAME_BUDGET_S = 0.25  # a frame slower than this would stall a 30 fps stage


class CoderLike(Protocol):
    @property
    def available(self) -> bool: ...

    def draft(self, request: Dict[str, Any]) -> tuple[str, str]: ...

    def repair(
        self, request: Dict[str, Any], code: str, error: str
    ) -> tuple[str, str]: ...


class VibeError(ValueError):
    """A request that cannot be honored (empty prompt, unknown pattern)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VibeCore:
    def __init__(
        self,
        vibe_dir: Path,
        registry: PatternRegistry,
        stage: StageCore,
        coder: CoderLike,
        *,
        models: Optional[List[str]] = None,
        backend: str = "api",
    ) -> None:
        self.dir = Path(vibe_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.stage = stage
        self.coder = coder
        self.models = list(models or [])
        self.backend = backend
        self._lock = threading.RLock()
        self._log_path = self.dir / "log.json"
        self.generations: List[Dict[str, Any]] = self._load_log()
        self._pending: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._working: Optional[Dict[str, Any]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Restart resilience: a request that was cooking when the server
        # died is left failed in the thread rather than silently lost.
        for entry in self.generations:
            if entry["status"] in ("queued", "cooking"):
                entry["status"] = "failed"
                entry["error"] = "server restarted before this finished"
        self._save_log()

    # ------------------------------------------------------------- the API

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            now = self.stage.snapshot()["now"]
            return {
                "enabled": self.coder.available,
                "backend": self.backend,
                "models": list(self.models),
                "now": self._playing(now),
                "queue": [dict(e) for e in self.generations if e["status"] == "queued"],
                "working": dict(self._working) if self._working else None,
                "generations": [dict(e) for e in reversed(self.generations)],
                "menu": self._menu(),
            }

    def submit(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Queue one prompt as generation #N (numbered now, so the crew
        sees it cooking) with the pattern showing at this moment
        captured as its context."""
        prompt = str(raw.get("prompt") or "").strip()
        if not prompt:
            raise VibeError("say what you want")
        model = str(raw.get("model") or "").strip() or (
            self.models[0] if self.models else ""
        )
        if self.models and model not in self.models:
            raise VibeError(f"unknown model {model!r}; pick one of {self.models}")
        with self._lock:
            now = self.stage.snapshot()["now"]
            shown = str(now.get("pattern") or "")
            n = len(self.generations) + 1
            entry: Dict[str, Any] = {
                "n": n,
                "pattern": f"{PATTERN_PREFIX}{n}",
                "name": str(raw.get("name") or "").strip()[:60],
                "author": str(raw.get("author") or "").strip()[:40],
                "prompt": prompt[:2000],
                "model": model,
                "shown": shown,
                "shown_title": self._title(shown),
                "from_scratch": bool(raw.get("from_scratch")),
                "note": "",
                "status": "queued",
                "error": "",
                "file": "",
                "seconds": None,
                "created": _now(),
            }
            self.generations.append(entry)
            self._save_log()
            request = dict(entry, shown_source=self.registry.source_of(shown) or "")
            self._pending.put(request)
            return dict(entry)

    def select(self, pattern: str) -> Dict[str, Any]:
        """Cut the stage to any pattern — a generation or a repo voice —
        which also makes it the context of the next prompt."""
        if pattern not in self.registry.patterns:
            raise VibeError(f"unknown pattern {pattern!r}")
        try:
            self.stage.cut({"pattern": pattern})
        except StageError as exc:
            raise VibeError(str(exc))
        return self.snapshot()

    # ------------------------------------------------------------ the work

    def process_one(self, block: bool = False, timeout: float = 0.5) -> bool:
        """Take one queued prompt through the model, the validator, the
        registry, and the stage. Returns False when nothing was queued."""
        try:
            request = self._pending.get(block=block, timeout=timeout if block else None)
        except queue.Empty:
            return False
        entry = self._entry(request["n"])
        with self._lock:
            entry["status"] = "cooking"
            self._working = entry
            self._save_log()
        started = time.monotonic()
        try:
            self._cook(request, entry)
        except (
            Exception
        ):  # a broken model call is a failed generation, not a dead worker
            entry["status"] = "failed"
            entry["error"] = traceback.format_exc(limit=2).strip()[-600:]
            logger.exception("vibe #%d failed", entry["n"])
        finally:
            with self._lock:
                entry["seconds"] = round(time.monotonic() - started, 1)
                self._working = None
                self._save_log()
        return True

    def _cook(self, request: Dict[str, Any], entry: Dict[str, Any]) -> None:
        n = entry["n"]
        code, note = self.coder.draft(request)
        source = self._stamp(code, entry)
        error = self.validate(source)
        if error is not None:
            self._keep(n, source, "attempt1")
            code, note2 = self.coder.repair(request, code, error)
            note = note2 or note
            source = self._stamp(code, entry)
            error = self.validate(source)
        entry["note"] = note[:400]
        if error is not None:
            entry["file"] = self._keep(n, source, "failed").name
            entry["status"] = "failed"
            entry["error"] = error.strip()[-600:]
            return
        path = self.dir / f"{PATTERN_PREFIX}{n:04d}.py"
        if path.exists():  # numbering is the identity; never overwrite
            raise RuntimeError(f"{path.name} already exists")
        path.write_text(source)
        entry["file"] = path.name
        self.registry.reload()
        load_error = self.registry.errors.get(str(path))
        if load_error is not None or entry["pattern"] not in self.registry.patterns:
            entry["status"] = "failed"
            entry["error"] = (load_error or "did not register").strip()[-600:]
            return
        entry["status"] = "ok"
        self.stage.cut({"pattern": entry["pattern"]})

    def validate(self, source: str) -> Optional[str]:
        """Load the module in a throwaway registry and run it on the real
        lights: a traceback, a bad shape, non-finite values, a frame
        over budget, or call-order dependence is the error text; None
        means it runs. Shared with the session backend's ship tool."""
        scratch = self.dir / "_scratch"
        scratch.mkdir(exist_ok=True)
        path = scratch / "candidate.py"
        path.write_text(source)
        try:
            probe = PatternRegistry([scratch])
        except Exception:
            return traceback.format_exc(limit=3)
        error = probe.errors.get(str(path))
        if error is not None:
            return error
        if not probe.patterns:
            return "no Pattern subclass found in the module"
        pattern = next(iter(probe.patterns.values()))
        lights = self.stage.engine.lights.array
        try:
            started = time.perf_counter()
            a = pattern.render(lights, 0.0)
            elapsed = time.perf_counter() - started
            b = pattern.render(lights, 7.31)
            again = pattern.render(lights, 0.0)
        except Exception:
            return traceback.format_exc(limit=4)
        n = lights.shape[0]
        for out in (a, b):
            if not isinstance(out, np.ndarray) or out.shape != (n, 3):
                return f"render must return an (n, 3) array; got {getattr(out, 'shape', type(out))}"
            if not np.all(np.isfinite(out)):
                return "render returned non-finite values"
        if not np.array_equal(a, again):
            return "render is not stateless: the same (lights, t) gave different output"
        if elapsed > FRAME_BUDGET_S:
            return f"a frame took {elapsed * 1000:.0f} ms; the stage budget is {FRAME_BUDGET_S * 1000:.0f} ms"
        return None

    # -------------------------------------------------------------- worker

    def start(self) -> None:
        """One background worker: prompts cook in order, one at a time."""
        if self._thread is not None:
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                self.process_one(block=True, timeout=0.5)

        self._thread = threading.Thread(target=loop, name="vibe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        close = getattr(self.coder, "close", None)  # a session backend holds one
        if callable(close):
            close()

    # ------------------------------------------------------------- helpers

    def _entry(self, n: int) -> Dict[str, Any]:
        return self.generations[n - 1]

    def _playing(self, now: Dict[str, Any]) -> Dict[str, Any]:
        pattern = str(now.get("pattern") or "")
        entry = self._generation_of(pattern)
        return {
            "pattern": pattern,
            "title": self._title(pattern),
            "n": entry["n"] if entry else None,
            "author": entry["author"] if entry else "",
            "prompt": entry["prompt"] if entry else "",
            "notes": now.get("notes") or "",
        }

    def _generation_of(self, pattern: str) -> Optional[Dict[str, Any]]:
        if not pattern.startswith(PATTERN_PREFIX):
            return None
        try:
            n = int(pattern[len(PATTERN_PREFIX) :])
        except ValueError:
            return None
        return self.generations[n - 1] if 0 < n <= len(self.generations) else None

    def _title(self, pattern: str) -> str:
        entry = self._generation_of(pattern)
        if entry is None:
            return pattern
        return f"#{entry['n']}" + (f" {entry['name']}" if entry["name"] else "")

    def _menu(self) -> Dict[str, Any]:
        """The side menu: named generations, all generations, then the
        repo's patterns by folder — anything here can be cut to."""
        done = [e for e in self.generations if e["status"] == "ok"]
        folders: Dict[str, List[Dict[str, str]]] = {}
        for row in self.registry.list():
            if not row.get("ok"):
                continue
            origin = self.registry.origin_of(str(row["name"]))
            if origin is None or origin[0] == self.dir:
                continue
            parts = Path(str(row["file"])).parts
            folder = "/".join(parts[:-1]) or "patterns"
            folders.setdefault(folder, []).append(
                {"name": str(row["name"]), "description": str(row["description"])}
            )
        repo = [
            {"folder": folder, "patterns": folders[folder]}
            for folder in sorted(folders, key=lambda f: (f != "patterns", f))
        ]
        summary = lambda e: {  # noqa: E731
            "n": e["n"],
            "pattern": e["pattern"],
            "name": e["name"],
            "author": e["author"],
            "prompt": e["prompt"],
        }
        return {
            "named": [summary(e) for e in reversed(done) if e["name"]],
            "all": [summary(e) for e in reversed(done)],
            "repo": repo,
        }

    def _keep(self, n: int, source: str, tag: str) -> Path:
        """Preserve a rejected draft beside the generations, under a
        leading underscore so the registry never loads it."""
        path = self.dir / f"_{PATTERN_PREFIX}{n:04d}-{tag}.py"
        k = 2
        while path.exists():
            path = self.dir / f"_{PATTERN_PREFIX}{n:04d}-{tag}-{k}.py"
            k += 1
        path.write_text(source)
        return path

    def _stamp(self, code: str, entry: Dict[str, Any]) -> str:
        """The generation's identity, written into the module: a header
        the humans can read, and ``name``/``description`` on its pattern
        class so the registry knows it as vibe-N."""
        line = lambda s: " ".join(str(s).split())  # noqa: E731 — one comment line
        header = [
            f"# vibe #{entry['n']}"
            + (f" — {line(entry['name'])}" if entry["name"] else ""),
            f"# by: {line(entry['author']) or 'someone at the sphere'}   "
            f"model: {entry['model'] or '?'}   {entry['created']}",
            f"# prompt: {line(entry['prompt'])}",
            f"# shown when typed: {entry['shown'] or '-'}"
            + ("  (started from scratch)" if entry["from_scratch"] else ""),
            "",
        ]
        description = entry["name"] or entry["prompt"][:72]
        return "\n".join(header) + assign_identity(code, entry["pattern"], description)

    # --------------------------------------------------------- persistence

    def _load_log(self) -> List[Dict[str, Any]]:
        try:
            doc = json.loads(self._log_path.read_text())
        except (OSError, ValueError):
            return []
        entries = doc.get("generations") if isinstance(doc, dict) else None
        return [dict(e) for e in entries] if isinstance(entries, list) else []

    def _save_log(self) -> None:
        tmp = self._log_path.with_name(self._log_path.name + ".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "generations": self.generations}, indent=2)
        )
        tmp.replace(self._log_path)


def assign_identity(code: str, name: str, description: str) -> str:
    """Set ``name`` (and a ``description`` if the class has none) on the
    first Pattern-like class in ``code`` — by AST position, so whatever
    the model called it, the registry knows it by its number."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"the module does not parse: {exc}") from exc
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not classes:
        raise ValueError("the module defines no class")
    target = next(
        (
            c
            for c in classes
            if any(
                isinstance(b, ast.FunctionDef) and b.name == "render" for b in c.body
            )
        ),
        classes[-1],  # a tuned registration inherits render
    )
    lines = code.splitlines()
    assigned: Dict[str, ast.stmt] = {}
    for node in target.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ("name", "description"):
                    assigned[t.id] = node
    indent = " " * (target.body[0].col_offset if target.body else target.col_offset + 4)
    if "name" in assigned:
        node = assigned["name"]
        end = node.end_lineno or node.lineno
        lines[node.lineno - 1 : end] = [f"{indent}name = {name!r}"]
        shift = end - node.lineno  # the splice may shrink later lines
    else:
        shift = 0
    if "description" not in assigned:
        # After the docstring if there is one, else first in the body.
        first = target.body[0]
        at = (
            (first.end_lineno or first.lineno)
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            else first.lineno - 1
        )
        insert_at = at - (
            shift if "name" in assigned and at > assigned["name"].lineno else 0
        )
        lines.insert(insert_at, f"{indent}description = {description!r}")
        if "name" not in assigned:
            lines.insert(insert_at, f"{indent}name = {name!r}")
    elif "name" not in assigned:
        node = assigned["description"]
        lines.insert(node.lineno - 1, f"{indent}name = {name!r}")
    return "\n".join(lines) + "\n"
