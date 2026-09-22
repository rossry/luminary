"""The vibe surface's Claude Code backend: one ongoing session, prompts in turn.

Where :class:`~luminary.vibe.coder.Coder` makes a single model call,
:class:`SessionCoder` keeps ONE Claude Code session open through the
Agent SDK and hands it the crew's prompts one after another — so it
remembers the night: what it shipped, what people asked, what it has
already read. It lives in the repo checkout with read-only tools (the
craft notes, the library, and every generation on disk under
``var/vibe/``), and it ships through one MCP tool of ours —
``ship_pattern`` — which validates the module against the real lights on
the spot and hands any failure straight back, so it iterates inside its
own turn. Whatever it says outside the tool is the note the crew sees.

The session runs on its own event loop in a background thread; the vibe
worker calls :meth:`draft` / :meth:`repair` synchronously, one at a time,
and waits. A session that breaks (the CLI died, a prompt ran past its
time) is dropped and the next prompt starts a fresh one; a session idle
for a while is closed. Both are lazy, so a quiet spell costs the startup
once, on the next prompt.

Both backends share the system prompt, the reply format, and the rule
that every prompt ships a best try. The session factory is injectable,
so the tests drive this path with a fake session and never spawn the CLI.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Protocol,
    TypeVar,
)

from luminary.vibe.coder import SYSTEM, extract

logger = logging.getLogger(__name__)

T = TypeVar("T")

Validator = Callable[[str], Optional[str]]  # source -> error text, or None if it runs


class SessionLike(Protocol):
    """What the coder needs from a session; ``ClaudeSDKClient`` has it all."""

    async def connect(self) -> None: ...

    async def query(self, prompt: str) -> None: ...

    def receive_response(self) -> AsyncIterator[Any]: ...

    async def set_model(self, model: Optional[str]) -> None: ...

    async def disconnect(self) -> None: ...


SessionFactory = Callable[[Dict[str, Any]], SessionLike]

TURN_TIMEOUT_S = 240.0  # a prompt still cooking after this is cut off
CONNECT_TIMEOUT_S = 60.0
IDLE_S = 20 * 60.0  # a session nobody has used for this long is closed

SESSION_ADDENDUM = """
YOU ARE ONE ONGOING CLAUDE CODE SESSION inside the Luminary checkout, with read-only tools. Prompts arrive one at a time from the people around the sphere, each carrying the pattern that was showing when it was typed. What you shipped earlier and what they asked are your memory — build on it when a prompt refers back ("like #3 but slower"). Every generation is on disk as `var/vibe/vibe-NNNN.py` (generation #N): Read one when the crew names a number you don't remember. You may Read `patterns/README.md` (the craft notes), `patterns/book-two/*.py` for the registration idiom, and the library under `luminary/patterns/` when you need a signature — once is enough; the crew is waiting.

SHIP THROUGH THE TOOL, EVERY PROMPT: call `ship_pattern` with the complete module source (and your short note). The server loads it against the real lights and either accepts it or returns exactly what broke — fix and ship again, up to a few times. Do not write files yourself. Your final text reply is your note to the crew (at most two sentences: a question or a comment). Always ship a best try before you stop.
"""

READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
SHIP_TOOL = "mcp__luminary__ship_pattern"
#: Auto mode: the deny list below still blocks first and the allow list
#: still pre-approves, so the classifier only ever sees a call outside
#: both — and nothing waits on a prompt nobody is there to answer. (The
#: CLI refuses ``bypassPermissions`` under root; auto has no such rule.)
DEFAULT_PERMISSION_MODE = "auto"
DENIED_TOOLS = [
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "Task",
    "Agent",
]


def sdk_available() -> bool:
    """The Agent SDK imports and a ``claude`` CLI is on PATH."""
    try:
        import claude_agent_sdk  # noqa: F401
    except Exception:
        return False
    return shutil.which("claude") is not None


class _Turn:
    """One prompt's collection point: what the session shipped and said."""

    def __init__(self) -> None:
        self.shipped: Dict[str, str] = {}
        self.said: List[str] = []
        self.failure = ""


class SessionCoder:
    def __init__(
        self,
        repo: Path,
        model: Optional[str] = None,
        validator: Optional[Validator] = None,
        session_factory: Optional[SessionFactory] = None,
        permission_mode: Optional[str] = None,
        turn_timeout: float = TURN_TIMEOUT_S,
        idle_s: float = IDLE_S,
    ) -> None:
        self.repo = Path(repo)
        self.model = model
        self.validator = validator or (lambda source: None)
        self.permission_mode = permission_mode or DEFAULT_PERMISSION_MODE
        self.turn_timeout = turn_timeout
        self.idle_s = idle_s
        self._factory: SessionFactory = session_factory or _sdk_session
        self._injected = session_factory is not None
        self.sessions_started = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._reaper: Optional["asyncio.Task[None]"] = None
        self._session: Optional[SessionLike] = None
        self._session_model: Optional[str] = None
        self._turn: Optional[_Turn] = None
        self._last_used = 0.0
        self._remembered: set[str] = set()  # generations THIS session shipped

    @property
    def available(self) -> bool:
        return self._injected or sdk_available()

    # ------------------------------------------------------------- the API

    def draft(self, request: Dict[str, Any]) -> tuple[str, str]:
        from luminary.vibe.coder import Coder

        prompt = Coder.brief(self._recalled(request))
        return self._run(self._ask(prompt, self._model_for(request), request))

    def repair(self, request: Dict[str, Any], code: str, error: str) -> tuple[str, str]:
        """A follow-up in the same conversation: what it shipped, what broke."""
        prompt = (
            "The module you just shipped failed on the server:\n"
            + error.strip()[-1500:]
            + "\n\nThe module:\n```python\n"
            + code
            + "```\nFix it and ship the corrected module."
        )
        return self._run(self._ask(prompt, self._model_for(request), request))

    def close(self) -> None:
        """Close the session, if any, and stop the loop thread."""
        loop, thread = self._loop, self._thread
        if loop is None:
            return
        try:
            self._run(self._shutdown())
        except Exception:  # a wedged session must not hold up shutdown
            logger.debug("vibe session shutdown", exc_info=True)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5.0)
        self._loop = None
        self._thread = None

    # -------------------------------------------------------- the prompt

    def _model_for(self, request: Dict[str, Any]) -> Optional[str]:
        model = request.get("model") or self.model
        return str(model) if model else None

    def _recalled(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """When the pattern showing is one THIS session shipped, a pointer
        replaces its source in the brief — the session remembers it, and
        the file is on disk if it doesn't."""
        shown = str(request.get("shown") or "")
        if shown not in self._remembered:
            return request
        try:
            n = int(shown.rsplit("-", 1)[-1])
        except ValueError:
            return request
        pointer = (
            f"# you shipped this one earlier in this session — generation #{n}, "
            f"file var/vibe/vibe-{n:04d}.py; Read it if you need the exact code"
        )
        return dict(request, shown_source=pointer)

    async def _ask(
        self, prompt: str, model: Optional[str], request: Dict[str, Any]
    ) -> tuple[str, str]:
        turn = _Turn()
        self._turn = turn
        self._last_used = time.monotonic()
        try:
            session = await self._connected(model)
            await asyncio.wait_for(
                self._exchange(session, prompt, turn), self.turn_timeout
            )
        except asyncio.TimeoutError:
            await self._drop()
            raise RuntimeError(
                f"the session took longer than {self.turn_timeout:.0f} s and was "
                "dropped; the next prompt starts a fresh one"
            )
        except Exception as exc:
            tail = _stderr_tail(self._session)
            await self._drop()
            if tail:
                raise RuntimeError(f"the claude session failed: {exc}\n{tail}") from exc
            raise
        finally:
            self._turn = None
            self._last_used = time.monotonic()
        note = " ".join(part.strip() for part in turn.said if part.strip())[:400]
        shipped = turn.shipped.get("code")
        if shipped is None:
            # The session talked but never shipped: a fenced block in its
            # words still counts (the core validates every draft anyway).
            shipped, spoken = extract("\n".join(turn.said))
            note = spoken or note
            if not shipped:
                raise RuntimeError(
                    turn.failure or "the session ended without shipping a pattern"
                )
        else:
            note = turn.shipped.get("note") or note
        self._remembered.add(str(request.get("pattern") or ""))
        return shipped, note

    async def _exchange(self, session: SessionLike, prompt: str, turn: _Turn) -> None:
        await session.query(prompt)
        async for message in session.receive_response():
            turn.said.extend(_texts(message))
            if type(message).__name__ == "ResultMessage" and getattr(
                message, "is_error", False
            ):
                turn.failure = str(
                    getattr(message, "result", None)
                    or getattr(message, "subtype", None)
                    or "the session reported an error"
                )

    async def _ship(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """The ``ship_pattern`` tool: validate now, answer ok or what broke."""
        turn = self._turn
        code = str(args.get("code") or "")
        note = str(args.get("note") or "")
        if turn is None:
            text = "no prompt is in progress — wait for the next one"
        else:
            error = self.validator(code) if code.strip() else "empty module"
            if error is None:
                turn.shipped["code"] = code if code.endswith("\n") else code + "\n"
                turn.shipped["note"] = note
                text = "ok: accepted — it runs on the sphere. Say your note and stop."
            else:
                text = "rejected:\n" + error.strip()[-1500:]
        return {"content": [{"type": "text", "text": text}]}

    def _options(self, model: Optional[str]) -> Dict[str, Any]:
        """Plain dict options; the SDK factory turns them into
        ``ClaudeAgentOptions`` (a fake factory just reads them)."""
        return {
            "cwd": str(self.repo),
            "model": model,
            "system_prompt": SYSTEM + SESSION_ADDENDUM,
            "allowed_tools": READ_ONLY_TOOLS + [SHIP_TOOL],
            "disallowed_tools": DENIED_TOOLS,
            "permission_mode": self.permission_mode,
            "setting_sources": [],
            "ship": self._ship,
        }

    # ------------------------------------------------------- the session

    async def _connected(self, model: Optional[str]) -> SessionLike:
        if self._session is None:
            session = self._factory(self._options(model))
            try:
                await asyncio.wait_for(session.connect(), CONNECT_TIMEOUT_S)
            except Exception as exc:
                tail = _stderr_tail(session)
                try:
                    await session.disconnect()
                except Exception:
                    pass
                raise RuntimeError(
                    f"the claude session failed to start: {exc}\n{tail}".rstrip()
                ) from exc
            self._session = session
            self._session_model = model
            self._remembered.clear()
            self.sessions_started += 1
            if self._reaper is None or self._reaper.done():
                self._reaper = asyncio.ensure_future(self._reap())
        elif model != self._session_model:
            await asyncio.wait_for(self._session.set_model(model), CONNECT_TIMEOUT_S)
            self._session_model = model
        return self._session

    async def _drop(self) -> None:
        session, self._session = self._session, None
        self._session_model = None
        self._remembered.clear()
        if session is not None:
            try:
                await asyncio.wait_for(session.disconnect(), 15.0)
            except Exception:  # it was already gone, most likely
                logger.debug("vibe session disconnect", exc_info=True)

    async def _shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
            await asyncio.sleep(0)
        await self._drop()

    async def _reap(self) -> None:
        """Close a session nobody has used for ``idle_s``; the next prompt
        starts a fresh one."""
        nap = max(min(30.0, self.idle_s / 4.0), 0.01)
        while True:
            await asyncio.sleep(nap)
            idle = time.monotonic() - self._last_used
            if self._session is not None and self._turn is None and idle > self.idle_s:
                logger.info("vibe: closing the session after %.0f s idle", idle)
                await self._drop()

    # ------------------------------------------------------------ the loop

    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run ``coro`` on the session's loop and wait for it (the worker
        is the only caller, and calls one at a time)."""
        future = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        return future.result(timeout=self.turn_timeout + CONNECT_TIMEOUT_S + 30.0)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        loop = asyncio.new_event_loop()

        def run() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_forever()
            finally:
                loop.close()

        self._thread = threading.Thread(target=run, name="vibe-session", daemon=True)
        self._thread.start()
        self._loop = loop
        return loop


def _texts(message: Any) -> List[str]:
    """Assistant text blocks out of an SDK message (duck-typed, so a fake
    session can yield plain objects)."""
    content = getattr(message, "content", None)
    if type(message).__name__ != "AssistantMessage" or not isinstance(content, list):
        return []
    return [
        str(block.text)
        for block in content
        if type(block).__name__ == "TextBlock" and getattr(block, "text", None)
    ]


def _stderr_tail(session: Any) -> str:
    """The CLI's own words when it fails (not logged in…), if the session
    kept them."""
    lines = getattr(session, "stderr", None) or []
    return "\n".join(str(line).strip() for line in lines if str(line).strip())[-800:]


class _SdkSession:
    """``ClaudeSDKClient`` plus the CLI's stderr, for the error text."""

    def __init__(self, client: Any, stderr: List[str]) -> None:
        self.client = client
        self.stderr = stderr

    async def connect(self) -> None:
        await self.client.connect()

    async def query(self, prompt: str) -> None:
        await self.client.query(prompt)

    def receive_response(self) -> AsyncIterator[Any]:
        response: AsyncIterator[Any] = self.client.receive_response()
        return response

    async def set_model(self, model: Optional[str]) -> None:
        await self.client.set_model(model)

    async def disconnect(self) -> None:
        await self.client.disconnect()


def _sdk_session(options: Dict[str, Any]) -> SessionLike:
    """The real thing: a long-lived Claude Code session through the Agent
    SDK's client, our ``ship_pattern`` tool served in-process."""
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        create_sdk_mcp_server,
        tool,
    )

    ship = options["ship"]

    async def ship_pattern(args: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = await ship(args)
        return result

    # Applied as a call, not decorator syntax: the SDK is an optional
    # extra, and mypy runs without it (the module is Any there).
    ship_tool = tool(
        "ship_pattern",
        "Ship the complete pattern module (and a short note for the crew). "
        "The server validates it on the real lights and answers ok, or "
        "returns exactly what broke so you can fix it and ship again.",
        {"code": str, "note": str},
    )(ship_pattern)

    server = create_sdk_mcp_server(name="luminary", tools=[ship_tool])
    stderr: List[str] = []
    sdk_options = ClaudeAgentOptions(
        cwd=options["cwd"],
        model=options["model"],
        system_prompt=options["system_prompt"],
        allowed_tools=options["allowed_tools"],
        disallowed_tools=options["disallowed_tools"],
        permission_mode=options["permission_mode"],
        setting_sources=options["setting_sources"],
        mcp_servers={"luminary": server},
        stderr=stderr.append,
    )
    return _SdkSession(ClaudeSDKClient(options=sdk_options), stderr)
