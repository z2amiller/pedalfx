"""Refuse to edit a project KiCad may be about to save over."""
import subprocess
from dataclasses import dataclass, field

from .discover import Project

KICAD_APP_PREFIX = "/Applications/KiCad/KiCad.app/Contents/MacOS/"


def process_commands() -> list:
    out = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True, check=False).stdout
    return out.splitlines()


def kicad_running(commands=None) -> bool:
    """True if any KiCad app process (kicad, pcbnew, eeschema…) is running. kicad-cli does not count."""
    for command in process_commands() if commands is None else commands:
        executable = command.strip().split(" ", 1)[0]
        if executable.startswith(KICAD_APP_PREFIX) and not executable.endswith("/kicad-cli"):
            return True
    return False


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    stale_locks: list = field(default_factory=list)


def check_guard(project: Project, force: bool = False, commands=None) -> GuardResult:
    locks = [path for path in project.lock_files if path.exists()]
    running = kicad_running(commands)
    if running and locks:
        return GuardResult(False, f"KiCad is running and {locks[0].name} exists; close the project first")
    if running and not force:
        return GuardResult(False, "KiCad is running (close it, or pass --force if this project is not open)")
    if locks:
        return GuardResult(True, "stale lock files ignored (KiCad is not running)", locks)
    return GuardResult(True)
