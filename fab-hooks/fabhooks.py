"""Shared helpers for JLCPCB generation hook scripts.

Stdlib only. All functions are pure or thin subprocess wrappers so the hook
entry points stay trivial and everything is testable offline.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

REV_RE = re.compile(r"^v\d+\.\d+$")
_GR_TEXT_REV_RE = re.compile(r'\(gr_text\s+"(v\d+\.\d+)"')
_TB_REV_RE = re.compile(r'\(rev\s+"([^"]*)"\)')


def balanced_block(text: str, start: int) -> str:
    """Return the substring of a balanced ( ... ) s-expression starting at start.

    Quote-aware: parens inside double-quoted strings (and \" escapes) are ignored.
    """
    depth = 0
    in_string = False
    i = start
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return text[start:]


def title_block_rev(board_text: str) -> str | None:
    """Rev string from the board's title_block, or None."""
    i = board_text.find("(title_block")
    if i < 0:
        return None
    m = _TB_REV_RE.search(balanced_block(board_text, i))
    return m.group(1) if m else None


def silk_rev(board_text: str) -> str | None:
    """First gr_text on a silkscreen layer matching vN.M, or None."""
    for m in _GR_TEXT_REV_RE.finditer(board_text):
        block = balanced_block(board_text, m.start())
        if re.search(r'\(layer\s+"[^"]*SilkS[^"]*"', block):
            return m.group(1)
    return None


def is_valid_rev(rev: str | None) -> bool:
    return bool(rev) and bool(REV_RE.fullmatch(rev))


def board_rev(board_path: Path | str) -> str | None:
    """Board revision: valid title-block rev first, silk v-text fallback, else None."""
    text = Path(board_path).read_text(encoding="utf-8")
    tb = title_block_rev(text)
    if is_valid_rev(tb):
        return tb
    return silk_rev(text)


FABLOG_NAME = "FABLOG.md"
FABLOG_HEADER = (
    "# Fab Log\n"
    "\n"
    "| Date | Board | Rev | Gen | Gerber SHA256 | JLC Order # | Notes |\n"
    "|---|---|---|---|---|---|---|\n"
)


def tag_name(board: str, rev: str, gen: str) -> str:
    return f"{board}-{rev}-g{gen}"


def commit_message(board: str, rev: str, gen: str) -> str:
    return f"{board} {rev} fab outputs (g{gen})"


def fablog_row(date_iso: str, board: str, rev: str, gen: str, sha12: str) -> str:
    return f"| {date_iso} | {board} | {rev} | {gen} | {sha12} | | |\n"


def sha256_file(path: Path | str, chars: int = 12) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:chars]


def append_fablog(repo_root: Path | str, row: str) -> Path:
    """Append a row to FABLOG.md at the repo root, creating it with header if absent."""
    log = Path(repo_root) / FABLOG_NAME
    if not log.exists():
        log.write_text(FABLOG_HEADER + row, encoding="utf-8")
    else:
        existing = log.read_text(encoding="utf-8")
        if not existing:
            log.write_text(FABLOG_HEADER + row, encoding="utf-8")
            return log
        prefix = "" if existing.endswith("\n") else "\n"
        with open(log, "a", encoding="utf-8") as f:
            f.write(prefix + row)
    return log


def git(repo: Path | str, *args: str, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run git in repo, capturing output. Raises CalledProcessError when check.

    GIT_TERMINAL_PROMPT=0 so a credential or host-key prompt fails fast in the
    headless hook context instead of blocking until the timeout.
    """
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        timeout=timeout,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def repo_root(path: Path | str) -> Path | None:
    """Repo toplevel containing path, or None."""
    try:
        r = git(Path(path), "rev-parse", "--show-toplevel", check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return Path(r.stdout.strip())


def origin_url(root: Path) -> str | None:
    try:
        r = git(root, "remote", "get-url", "origin", check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def origin_reachable(root: Path, timeout: int = 5) -> bool:
    """True if origin can be contacted, regardless of whether it has any refs yet.

    Deliberately omits --exit-code and a pinned ref (e.g. HEAD): a freshly
    created bare origin has no refs at all, and its symbolic HEAD may point at
    a branch name (e.g. "master") that was never created, so pinning to HEAD
    with --exit-code reports "unreachable" for a perfectly reachable remote.
    Non-zero here (typically 128) means the remote genuinely could not be
    contacted.
    """
    try:
        r = git(root, "ls-remote", "origin", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def tag_exists(root: Path, tag: str) -> bool:
    try:
        r = git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0
