"""Pattern discovery, loading, and hot-reload (spec §9.3).

The registry is the single source of "available patterns" for the CLI and the
API. reload() re-executes changed files with error isolation: one broken
pattern file becomes a reported error, never a crash (spec §9.3.1, §15.5.1).
"""

from __future__ import annotations

import sys
import traceback
import types
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from luminary.patterns.base import Pattern


class PatternRegistry:
    """Discovers Pattern subclasses in one or more directories."""

    def __init__(self, directories: Sequence[Union[str, Path]]):
        self.directories = [Path(d) for d in directories]
        self.patterns: Dict[str, Pattern] = {}
        self.errors: Dict[str, str] = {}
        self._by_stem: Dict[str, str] = {}
        self._load_counter = 0
        self.reload()

    def reload(self) -> None:
        """Re-scan all directories and re-execute pattern modules."""
        self._load_counter += 1
        patterns: Dict[str, Pattern] = {}
        errors: Dict[str, str] = {}
        by_stem: Dict[str, str] = {}

        for directory in self.directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                try:
                    loaded = self._load_file(path)
                except Exception:
                    errors[str(path)] = traceback.format_exc(limit=3)
                    continue
                if loaded is None:
                    errors[str(path)] = "No Pattern subclass found"
                    continue
                if loaded.name in patterns:
                    errors[str(path)] = (
                        f"Duplicate pattern name {loaded.name!r} "
                        f"(already provided by another file)"
                    )
                    continue
                patterns[loaded.name] = loaded
                by_stem[path.stem] = loaded.name

        self.patterns = patterns
        self.errors = errors
        self._by_stem = by_stem

    def _load_file(self, path: Path) -> Optional[Pattern]:
        # A fresh module name per reload forces true re-execution, and
        # compiling the source directly bypasses the __pycache__ bytecode
        # cache — whose (mtime-seconds, size) key would serve stale code for
        # a file re-saved within the same second (the common hot-swap case).
        module_name = f"_luminary_pattern_{path.stem}_{self._load_counter}"
        source = path.read_text()
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        sys.modules[module_name] = module
        try:
            exec(compile(source, str(path), "exec"), module.__dict__)
        finally:
            sys.modules.pop(module_name, None)
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Pattern)
                and obj is not Pattern
                and obj.__module__ == module_name
            ):
                return obj()
        return None

    def get(self, name: str) -> Pattern:
        """Look up by pattern name (or file stem as a convenience)."""
        if name in self.patterns:
            return self.patterns[name]
        if name in self._by_stem:
            return self.patterns[self._by_stem[name]]
        available = ", ".join(sorted(self.patterns)) or "(none)"
        raise KeyError(f"Unknown pattern {name!r}; available: {available}")

    def list(self) -> List[dict]:
        """Metadata for every discovered pattern plus load errors (spec §15.3)."""
        entries = [
            {"name": pattern.name, "description": pattern.description, "ok": True}
            for pattern in sorted(self.patterns.values(), key=lambda p: p.name)
        ]
        entries.extend(
            {"name": file, "description": error.strip().splitlines()[-1], "ok": False}
            for file, error in sorted(self.errors.items())
        )
        return entries


def default_registry(extra_dirs: Sequence[Union[str, Path]] = ()) -> PatternRegistry:
    """Registry over the repo patterns/ directory plus any extras (uploads)."""
    repo_patterns = Path(__file__).resolve().parents[2] / "patterns"
    return PatternRegistry([repo_patterns, *extra_dirs])
