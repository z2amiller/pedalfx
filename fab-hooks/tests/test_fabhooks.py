"""Tests for fabhooks library."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fabhooks

BOARD_WITH_REV = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(title_block
\t\t(title "Test Board")
\t\t(rev "v0.3")
\t)
\t(gr_text "v9.9"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_TEMPLATE_REV = BOARD_WITH_REV.replace('(rev "v0.3")', '(rev "1.0")')
BOARD_NO_TITLE_BLOCK = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(gr_text "v0.7"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""


def _write(tmp_path, text):
    p = tmp_path / "board.kicad_pcb"
    p.write_text(text)
    return p


def test_board_rev_from_title_block(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_WITH_REV)) == "v0.3"


def test_board_rev_title_block_wins_over_silk(tmp_path):
    # silk says v9.9 but the title block is authoritative
    assert fabhooks.board_rev(_write(tmp_path, BOARD_WITH_REV)) != "v9.9"


def test_board_rev_template_junk_falls_back_to_silk(tmp_path):
    # "1.0" fails validation, so the silk v-text is used
    assert fabhooks.board_rev(_write(tmp_path, BOARD_TEMPLATE_REV)) == "v9.9"


def test_board_rev_no_title_block_uses_silk(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_NO_TITLE_BLOCK)) == "v0.7"


def test_is_valid_rev():
    assert fabhooks.is_valid_rev("v0.1")
    assert fabhooks.is_valid_rev("v12.3")
    assert not fabhooks.is_valid_rev("1.0")
    assert not fabhooks.is_valid_rev("v1")
    assert not fabhooks.is_valid_rev("")
    assert not fabhooks.is_valid_rev(None)
