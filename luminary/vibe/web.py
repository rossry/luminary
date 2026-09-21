"""Web adapter for vibe mode: the page and its three routes.

Thin (implementation-notes §2.9): ``GET /vibe`` serves the page,
``GET /api/vibe`` is the whole shared state, ``POST /api/vibe`` queues a
prompt, ``POST /api/vibe/select`` cuts to a pattern. Mutations hang on
the same stage-key guard as the queue. The canvas on the page decodes
the stage's own wire stream (``WS /api/stage``) — vibe mode has no
second render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from luminary.stage.web import stage_key_guard
from luminary.vibe.core import VibeCore, VibeError

_STATIC = Path(__file__).resolve().parents[1] / "server" / "static"


def register_vibe(
    app: FastAPI, core: VibeCore, *, stage_key: Optional[str] = None
) -> None:
    guarded = [Depends(stage_key_guard(stage_key))]
    app.state.vibe = core

    @app.get("/vibe", response_class=HTMLResponse)
    def vibe_page() -> str:
        return (_STATIC / "vibe.html").read_text()

    @app.get("/api/vibe")
    def vibe_state() -> JSONResponse:
        return JSONResponse(core.snapshot())

    @app.post("/api/vibe", dependencies=guarded)
    def vibe_submit(body: Dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(core.submit(body), status_code=202)
        except VibeError as exc:
            raise HTTPException(422, detail=str(exc))

    @app.post("/api/vibe/select", dependencies=guarded)
    def vibe_select(body: Dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(core.select(str(body.get("pattern") or "")))
        except VibeError as exc:
            raise HTTPException(404, detail=str(exc))
