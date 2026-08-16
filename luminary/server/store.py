"""Filesystem-backed geometry store (spec §15.6).

Documents are content-addressed: id = short SHA-1 of the canonical JSON, so
identical saves dedupe. No database — inspectable, git-friendly files:
``store/scaffolds/<id>.scaffold.json`` and ``store/lights/<id>.lights.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

_KIND_SUFFIX = {"scaffolds": ".scaffold.json", "lights": ".lights.json"}


class Store:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        for kind in _KIND_SUFFIX:
            (self.base_dir / kind).mkdir(parents=True, exist_ok=True)

    def _dir(self, kind: str) -> Path:
        if kind not in _KIND_SUFFIX:
            raise ValueError(f"Unknown store kind {kind!r}")
        return self.base_dir / kind

    def save(self, kind: str, doc: Dict[str, Any]) -> str:
        canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        doc_id = hashlib.sha1(canonical.encode()).hexdigest()[:10]
        path = self._dir(kind) / f"{doc_id}{_KIND_SUFFIX[kind]}"
        if not path.exists():
            path.write_text(json.dumps(doc, indent=2))
        return doc_id

    def get(self, kind: str, doc_id: str) -> Dict[str, Any]:
        path = self._dir(kind) / f"{doc_id}{_KIND_SUFFIX[kind]}"
        if not path.exists():
            raise KeyError(f"No {kind[:-1]} with id {doc_id!r}")
        result: Dict[str, Any] = json.loads(path.read_text())
        return result

    def list(self, kind: str) -> List[Dict[str, Any]]:
        suffix = _KIND_SUFFIX[kind]
        entries = []
        for path in sorted(self._dir(kind).glob(f"*{suffix}")):
            doc_id = path.name[: -len(suffix)]
            try:
                doc = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            entry: Dict[str, Any] = {
                "id": doc_id,
                "name": doc.get("meta", {}).get("name"),
            }
            if kind == "lights":
                entry["n_lights"] = len(doc.get("lights", []))
            else:
                entry["n_lines"] = len(doc.get("lines", []))
            entries.append(entry)
        return entries
