"""Shared helpers for JLCPCB generation hook scripts.

Stdlib only. All functions are pure or thin subprocess wrappers so the hook
entry points stay trivial and everything is testable offline.
"""
from __future__ import annotations

import re
from pathlib import Path

REV_RE = re.compile(r"^v\d+\.\d+$")
_SILK_REV_RE = re.compile(r'\(gr_text\s+"(v\d+\.\d+)"')
_TB_REV_RE = re.compile(r'\(rev\s+"([^"]*)"\)')


def balanced_block(text: str, start: int) -> str:
    """Return the substring of a balanced ( ... ) s-expression starting at start."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def title_block_rev(board_text: str):
    """Rev string from the board's title_block, or None."""
    i = board_text.find("(title_block")
    if i < 0:
        return None
    m = _TB_REV_RE.search(balanced_block(board_text, i))
    return m.group(1) if m else None


def silk_rev(board_text: str):
    """First silk/graphic text matching vN.M, or None."""
    m = _SILK_REV_RE.search(board_text)
    return m.group(1) if m else None


def is_valid_rev(rev) -> bool:
    return bool(rev) and bool(REV_RE.match(rev))


def board_rev(board_path: Path):
    """Board revision: valid title-block rev first, silk v-text fallback, else None."""
    text = Path(board_path).read_text(encoding="utf-8")
    tb = title_block_rev(text)
    if is_valid_rev(tb):
        return tb
    return silk_rev(text)
