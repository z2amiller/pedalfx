#!/usr/bin/env python3
"""Set the title-block revision in a .kicad_pcb file. Close KiCad first.

Usage: set_board_rev.py path/to/board.kicad_pcb v0.1
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabhooks

_TB_REV_RE = re.compile(r'\(rev "([^"]*)"\)')


def set_rev(board_path: Path, rev: str) -> str:
    """Set title-block rev; returns the previous rev ('' if none). Raises on problems."""
    board_path = Path(board_path)
    if not fabhooks.is_valid_rev(rev):
        raise ValueError(f"revision {rev!r} must match vN.M (e.g. v0.1)")
    lock = board_path.parent / f"~{board_path.name}.lck"
    if lock.exists():
        raise RuntimeError(f"KiCad lock file present ({lock.name}) -- close KiCad first")
    text = board_path.read_text(encoding="utf-8")
    i = text.find("(title_block")
    if i < 0:
        raise RuntimeError(
            "no title_block in board file -- set any revision once in KiCad "
            "(File > Board Setup > Title Block), then re-run"
        )
    block = fabhooks.balanced_block(text, i)
    m = _TB_REV_RE.search(block)
    if m:
        old = m.group(1)
        new_block = block.replace(m.group(0), f'(rev "{rev}")', 1)
    else:
        old = ""
        new_block = block.replace("(title_block", f'(title_block\n\t\t(rev "{rev}")', 1)
    board_path.write_text(text.replace(block, new_block, 1), encoding="utf-8")
    return old


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 1
    board, rev = Path(argv[0]), argv[1]
    try:
        old = set_rev(board, rev)
    except (ValueError, RuntimeError) as e:
        print(f"FAIL: {e}")
        return 1
    print(f"{board.name}: rev {old!r} -> {rev!r}. Open the board in KiCad to verify.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
