"""Shared helpers for JLCPCB generation hook scripts.

Stdlib only. All functions are pure or thin subprocess wrappers so the hook
entry points stay trivial and everything is testable offline.
"""
from __future__ import annotations

import hashlib
import re
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


def sha256_file(path: Path, chars: int = 12) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:chars]


def append_fablog(repo_root: Path, row: str) -> Path:
    """Append a row to FABLOG.md at the repo root, creating it with header if absent."""
    log = Path(repo_root) / FABLOG_NAME
    if not log.exists():
        log.write_text(FABLOG_HEADER + row, encoding="utf-8")
    else:
        with open(log, "a", encoding="utf-8") as f:
            f.write(row)
    return log
