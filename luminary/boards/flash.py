"""Build and flash Scorpio firmware, then prove the board came back.

The flow per board, and why each step is here:

1. **Build** with the board's controller id compiled in. The id is a build
   flag, not runtime state (spec §13.6), so every board needs its own binary.
2. **Enter BOOTSEL.** A flashed board is a USB-CDC device; opening its port
   at 1200 baud is the standard "1200 bps touch" that the arduino-pico core
   answers by resetting into the ROM bootloader. A board that is already in
   BOOTSEL — or has no working firmware to touch — skips straight to step 3,
   which is what makes an unflashed or bricked board recoverable.
3. **Copy the UF2** onto the RPI-RP2 volume. The bootloader reboots itself
   when the write completes; there is no separate "start" command.
4. **Verify.** Re-probe until the board enumerates again and answers with the
   id we just compiled in. Without this the command can only report that a
   file copy succeeded, which is not the same as a working board — the
   failure this whole module exists to catch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from luminary.boards import discovery

REPO = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = REPO / "firmware" / "scorpio"
# One env for every board: the controller id and any strip overrides arrive
# as build flags, so ids beyond the hand-written controller0/controller1 envs
# need no edit to platformio.ini.
DEPLOY_ENV = "deploy"

BOOTSEL_TOUCH_BAUD = 1200
BOOTSEL_WAIT = 15.0
REENUMERATE_WAIT = 30.0


@dataclass
class FlashResult:
    controller: int
    ok: bool
    detail: str
    port: Optional[str] = None
    uf2: Optional[Path] = None


def uf2_path(env_name: str = DEPLOY_ENV, project_dir: Path = FIRMWARE_DIR) -> Path:
    return project_dir / ".pio" / "build" / env_name / "firmware.uf2"


def build_firmware(
    controller: int,
    *,
    max_per_strip: Optional[int] = None,
    color_order: Optional[str] = None,
    project_dir: Path = FIRMWARE_DIR,
    env_name: str = DEPLOY_ENV,
    pio: Optional[str] = None,
    quiet: bool = False,
) -> Path:
    """Compile firmware for one controller id; -> the built UF2.

    Flags go through ``PLATFORMIO_BUILD_FLAGS`` rather than a command-line
    option: ``pio run`` has no ``--build-flag`` (the header comment in
    platformio.ini notwithstanding), and the environment variable is
    appended to the env's own ``build_flags``, which is exactly the
    override semantics wanted here.
    """
    flags = [f"-DLUMINARY_CONTROLLER_ID={controller}"]
    if max_per_strip is not None:
        flags.append(f"-DLUMINARY_MAX_PER_STRIP={max_per_strip}")
    if color_order is not None:
        flags.append(f"-DLUMINARY_COLOR_ORDER={color_order}")

    env = dict(os.environ)
    env["PLATFORMIO_BUILD_FLAGS"] = " ".join(flags)

    command = [pio or _pio_executable(), "run", "-e", env_name]
    if quiet:
        command.append("--silent")
    result = subprocess.run(
        command, cwd=str(project_dir), env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"firmware build failed for controller {controller}:\n"
            + (result.stdout or "")
            + (result.stderr or "")
        )
    built = uf2_path(env_name, project_dir)
    if not built.exists():
        raise RuntimeError(f"build reported success but {built} is missing")
    return built


def _pio_executable() -> str:
    """The pio on PATH, or the one alongside this interpreter."""
    found = shutil.which("pio")
    if found:
        return found
    import sys

    candidate = Path(sys.executable).parent / "pio"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(
        "PlatformIO not found: install it with `pip install platformio` "
        "into the environment running luminary"
    )


def enter_bootsel(port: str) -> bool:
    """1200 bps touch: ask a running board to reset into its bootloader.

    Returns whether the touch was delivered, not whether the board obeyed —
    the caller confirms that by waiting for the volume to appear. Errors are
    swallowed deliberately: the port disappears out from under the close()
    precisely when the touch *worked*.
    """
    try:
        import serial
    except ImportError:
        return False
    try:
        conn = serial.Serial(port, baudrate=BOOTSEL_TOUCH_BAUD, timeout=0)
    except (OSError, ValueError):
        return False
    try:
        conn.dtr = False
        time.sleep(0.05)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return True


def wait_for_bootsel(timeout: float = BOOTSEL_WAIT) -> Optional[Path]:
    """Poll until the RPI-RP2 volume is mounted; -> its path."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        mount = discovery._bootsel_mount()
        if mount is not None:
            return mount
        time.sleep(0.25)
    return None


def write_uf2(uf2: Path, mount: Path) -> None:
    """Copy the image and flush it; the bootloader reboots on completion."""
    shutil.copy(str(uf2), str(mount / uf2.name))
    os.sync()


def wait_for_board(controller: int, timeout: float = REENUMERATE_WAIT) -> Optional[str]:
    """Poll until a board answers with ``controller``; -> its port.

    This is the step that distinguishes "the UF2 copied" from "the board
    works": it re-enumerates USB and re-runs the protocol identity probe,
    so a board that boots but never brings up USB, or comes up with the
    wrong id, is reported as a failure rather than a success.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ports = discovery.boards_by_controller(discovery.discover(timeout=0.5))
        if controller in ports:
            return ports[controller]
        time.sleep(0.5)
    return None


def flash_board(
    controller: int,
    *,
    port: Optional[str] = None,
    max_per_strip: Optional[int] = None,
    color_order: Optional[str] = None,
    verify: bool = True,
    log: Optional[object] = None,
) -> FlashResult:
    """Build, flash, and verify one board."""

    def say(message: str) -> None:
        if log is not None:
            print(message, file=log)  # type: ignore[call-overload]

    say(f"controller {controller}: building firmware")
    try:
        uf2 = build_firmware(
            controller, max_per_strip=max_per_strip, color_order=color_order
        )
    except RuntimeError as exc:
        return FlashResult(controller, False, str(exc))

    mount = discovery._bootsel_mount()
    if mount is None and port is not None:
        say(f"controller {controller}: resetting {port} into BOOTSEL")
        enter_bootsel(port)
        mount = wait_for_bootsel()
    elif mount is None:
        mount = wait_for_bootsel(timeout=1.0)

    if mount is None:
        return FlashResult(
            controller,
            False,
            "no RPI-RP2 volume appeared: hold BOOTSEL while plugging the "
            "board in, then re-run",
            uf2=uf2,
        )

    say(f"controller {controller}: writing {uf2.name} to {mount}")
    try:
        write_uf2(uf2, mount)
    except OSError as exc:
        return FlashResult(controller, False, f"copy failed: {exc}", uf2=uf2)

    if not verify:
        return FlashResult(controller, True, "written (not verified)", uf2=uf2)

    say(f"controller {controller}: waiting for the board to come back")
    found = wait_for_board(controller)
    if found is None:
        # A freshly flashed board is a brand-new device node, so the usual
        # reason it cannot be verified is that the node is not readable --
        # report that specifically instead of blaming the firmware.
        blocked = [
            c for c in discovery.discover(timeout=0.5) if c.status == discovery.BLOCKED
        ]
        if blocked:
            return FlashResult(
                controller,
                False,
                "flashed, but the board's port could not be opened to verify "
                f"it: {blocked[0].detail}",
                port=blocked[0].device,
                uf2=uf2,
            )
        return FlashResult(
            controller,
            False,
            "flashed, but no board answered with this controller id — it did "
            "not re-enumerate, or came up with a different id",
            uf2=uf2,
        )
    return FlashResult(controller, True, "flashed and verified", port=found, uf2=uf2)


def targets_from(
    registry_ports: dict, candidates: List[discovery.Candidate]
) -> List[int]:
    """Controller ids worth flashing: registered boards, live boards, and —
    when nothing else is known — controller 0 for a lone BOOTSEL board."""
    ids = set(registry_ports)
    ids.update(
        c.controller for c in candidates if c.is_board and c.controller is not None
    )
    if not ids and any(c.status == discovery.BOOTSEL for c in candidates):
        ids = {0}
    return sorted(ids)
