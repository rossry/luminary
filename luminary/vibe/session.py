"""The vibe surface's Claude Code backend: one agent session per prompt.

Where :class:`~luminary.vibe.coder.Coder` makes a single model call,
:class:`SessionCoder` hands the prompt to a real Claude Code session run
through the Agent SDK (the programmatic connector for a session): it
lives in the repo checkout with read-only tools, so it can consult
``patterns/README.md`` and the library while it writes, and it ships its
answer through one MCP tool of ours — ``ship_pattern`` — which validates
the module against the real lights on the spot and hands any failure
straight back, so the session iterates inside its own turn. Whatever it
says outside the tool is the note the crew sees.

Both backends share the system prompt, the reply format, and the rule
that every prompt ships a best try. The session runner is injectable, so
the tests drive this path with a fake session and never spawn the CLI.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from luminary.vibe.coder import SYSTEM, extract

Validator = Callable[[str], Optional[str]]  # source -> error text, or None if it runs
Runner = Callable[[str, Dict[str, Any]], AsyncIterator[Any]]

MAX_TURNS = 14

SESSION_ADDENDUM = """
YOU ARE A CLAUDE CODE SESSION inside the Luminary checkout, with read-only tools. You may Read `patterns/README.md` (the craft notes), look at `patterns/book-two/*.py` for the registration idiom, and read the library under `luminary/patterns/` when you need a signature — but keep it quick: the crew is waiting at the sphere.

SHIP THROUGH THE TOOL: call `ship_pattern` with the complete module source (and your short note). The server loads it against the real lights and either accepts it or returns exactly what broke — fix and ship again, up to a few times. Do not write files yourself. Your final text reply is your note to the crew (at most two sentences: a question or a comment). Always ship a best try before you stop.
"""

READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
SHIP_TOOL = "mcp__luminary__ship_pattern"
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


class SessionCoder:
    def __init__(
        self,
        repo: Path,
        model: Optional[str] = None,
        validator: Optional[Validator] = None,
        runner: Optional[Runner] = None,
    ) -> None:
        self.repo = Path(repo)
        self.model = model
        self.validator = validator or (lambda source: None)
        self._runner = runner

    @property
    def available(self) -> bool:
        return self._runner is not None or sdk_available()

    # ------------------------------------------------------------ the turn

    def draft(self, request: Dict[str, Any]) -> tuple[str, str]:
        from luminary.vibe.coder import Coder

        prompt = Coder.brief(request)
        return asyncio.run(self._turn(prompt, request.get("model") or self.model))

    def repair(self, request: Dict[str, Any], code: str, error: str) -> tuple[str, str]:
        """The session already iterates against the validator inside its
        turn; a second full turn carries the failure forward."""
        from luminary.vibe.coder import Coder

        prompt = (
            Coder.brief(request)
            + "\n\nYour previous module:\n```python\n"
            + code
            + "```\nIt failed on the server:\n"
            + error.strip()[-1500:]
            + "\nFix it and ship the corrected module."
        )
        return asyncio.run(self._turn(prompt, request.get("model") or self.model))

    async def _turn(self, prompt: str, model: Optional[str]) -> tuple[str, str]:
        shipped: Dict[str, str] = {}
        said: List[str] = []

        async def ship(args: Dict[str, Any]) -> Dict[str, Any]:
            code = str(args.get("code") or "")
            note = str(args.get("note") or "")
            error = self.validator(code) if code.strip() else "empty module"
            if error is None:
                shipped["code"] = code if code.endswith("\n") else code + "\n"
                shipped["note"] = note
                text = "ok: accepted — it runs on the sphere. Say your note and stop."
            else:
                text = "rejected:\n" + error.strip()[-1500:]
            return {"content": [{"type": "text", "text": text}]}

        options = self._options(model, ship)
        async for message in self._messages(prompt, options):
            for text in _texts(message):
                said.append(text)
        note = " ".join(part.strip() for part in said if part.strip())[:400]
        if "code" in shipped:
            return shipped["code"], shipped.get("note") or note
        # The session talked but never shipped: a fenced block in its
        # words still counts (the core validates every draft anyway).
        code, spoken = extract("\n".join(said))
        if code:
            return code, spoken or note
        raise RuntimeError("the session ended without shipping a pattern")

    def _options(
        self, model: Optional[str], ship: Callable[[Dict[str, Any]], Awaitable[Any]]
    ) -> Dict[str, Any]:
        """Plain dict options; turned into ``ClaudeAgentOptions`` by the
        SDK runner (a fake runner just reads them)."""
        return {
            "cwd": str(self.repo),
            "model": model,
            "system_prompt": SYSTEM + SESSION_ADDENDUM,
            "allowed_tools": READ_ONLY_TOOLS + [SHIP_TOOL],
            "disallowed_tools": DENIED_TOOLS,
            # Everything it may touch is pre-approved above, so the default
            # mode never prompts; bypassing is refused by the CLI under root.
            "permission_mode": "default",
            "max_turns": MAX_TURNS,
            "setting_sources": [],
            "ship": ship,
        }

    def _messages(self, prompt: str, options: Dict[str, Any]) -> AsyncIterator[Any]:
        if self._runner is not None:
            return self._runner(prompt, options)
        return _sdk_runner(prompt, options)


def _texts(message: Any) -> List[str]:
    """Assistant text blocks out of an SDK message (duck-typed, so the
    fake runner can yield plain objects)."""
    content = getattr(message, "content", None)
    if type(message).__name__ != "AssistantMessage" or not isinstance(content, list):
        return []
    return [
        str(block.text)
        for block in content
        if type(block).__name__ == "TextBlock" and getattr(block, "text", None)
    ]


async def _sdk_runner(prompt: str, options: Dict[str, Any]) -> AsyncIterator[Any]:
    """The real thing: a Claude Code session through the Agent SDK, our
    ``ship_pattern`` tool served in-process."""
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        create_sdk_mcp_server,
        query,
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
    stderr: List[str] = []  # the CLI's own words when it fails (not logged in…)
    sdk_options = ClaudeAgentOptions(
        cwd=options["cwd"],
        model=options["model"],
        system_prompt=options["system_prompt"],
        allowed_tools=options["allowed_tools"],
        disallowed_tools=options["disallowed_tools"],
        permission_mode=options["permission_mode"],
        max_turns=options["max_turns"],
        setting_sources=options["setting_sources"],
        mcp_servers={"luminary": server},
        stderr=stderr.append,
    )
    try:
        async for message in query(prompt=prompt, options=sdk_options):
            yield message
    except Exception as exc:
        tail = "\n".join(line.strip() for line in stderr if line.strip())[-800:]
        if not tail:
            raise
        raise RuntimeError(f"the claude session failed: {exc}\n{tail}") from exc
