"""Tests for the 1590XX template build: geometry constants and the board checker (stdlib + pytest)."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import geometry  # noqa: E402
from check_full1590xx import check  # noqa: E402

FULL125 = HERE.parent / "Full125Template"


def test_tayda_map():
    assert geometry.tayda_to_board(-38.0, 55.0) == pytest.approx((92.5, 62.75))
    assert geometry.tayda_to_board(45.0, 0.0) == pytest.approx((147.5, 145.75))


def test_guides_complete():
    assert len(geometry.GUIDES) == 12 + 4 + 3 + 3


def test_header_pin1():
    assert geometry.header_pin1(185.5) == pytest.approx((176.39, 133.03))


def test_clearances_numeric():
    flange_bottom = geometry.LED_Y + 2.9
    pad_top = geometry.HEADER_Y - geometry.HEADER_PAD / 2
    assert pad_top - flange_bottom >= 1.0
    assert pad_top - flange_bottom == pytest.approx(1.13, abs=0.01)
    assert (geometry.SWITCH_Y - geometry.SW_COURTYARD_Y) - geometry.BOTTOM_Y >= 2.0


def test_check_fails_on_full125():
    msgs = check(FULL125 / "fx-Full125B.kicad_pcb", FULL125)
    text = "\n".join(msgs)
    assert "User.2 guide missing" in text
    assert "J104 position" in text


def _board(*footprints):
    return "(kicad_pcb\n\t(version 20250114)\n\t(generator \"test\")\n" + "".join(footprints) + ")\n"


def _fp(ref, lib, layer, x, y, rot, pads):
    pad_txt = "".join(f'\n\t\t(pad "{n}" thru_hole circle\n\t\t\t(at {px} {py} {rot})\n\t\t\t(size 1.7 1.7)\n\t\t)'
                      for n, px, py in pads)
    return (f'\t(footprint "{lib}"\n\t\t(layer "{layer}")\n\t\t(at {x} {y} {rot})\n'
            f'\t\t(property "Reference" "{ref}"\n\t\t\t(at 0 0 0)\n\t\t)' + pad_txt + "\n\t)\n")


def test_header_pin1_west(tmp_path):
    # pin 1 at the right spot but rotated 270, so the row runs west and pin 1 ends up east of pin 8
    x, y = geometry.header_pin1(geometry.SWITCH_X[0])
    pads = [(str(n), 0, 2.54 * (n - 1)) for n in range(1, 9)]
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("J101", "Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical", "F.Cu", x, y, 270, pads)))
    assert any("J101 pin 1 not west" in m for m in check(p))


def test_led_body_centre(tmp_path):
    # D102 origin (pad 1) placed on the body centre: the body centre is then 1.27 mm off
    cx, cy, rot, layer = geometry.FOOTPRINTS["D102"]
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("D102", "LED_THT:LED_D5.0mm", layer, cx, cy, rot, [("1", 0, 0), ("2", 2.54, 0)])))
    assert any("D102 body centre" in m for m in check(p))
