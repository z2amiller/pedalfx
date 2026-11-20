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
    assert len(geometry.GUIDES) == 12 + 4 + 3 + 3 + 2      # pots, row 3, footswitches, LEDs, side-C jacks
    jacks = {round(x, 2): d for label, x, _y, d in geometry.GUIDES if "JACK" in label}
    assert jacks == {109.5: 12.8, 185.5: 12.8}


def test_header_pin1():
    # util-TinyFootSwitch: header J4 centre 110.025, switch (B2) 109.8 -> the header sits 0.225 mm EAST of the switch
    assert geometry.header_pin1(185.5) == pytest.approx((176.835, 133.03))


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
    assert "User.2 DC jack guide missing" in text


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


def test_pillar_ignores_enclosure_outline(tmp_path):
    # L7's User.4 holds the whole enclosure rectangle (reaching y 160.7) as well as the corner bosses; only the
    # bosses (everything below y 150) count as pillars
    def gr_rect(a, b):
        return (f'\t(gr_rect\n\t\t(start {a[0]} {a[1]})\n\t\t(end {b[0]} {b[1]})\n\t\t(stroke\n\t\t\t(width 0.1)\n'
                f'\t\t\t(type default)\n\t\t)\n\t\t(fill no)\n\t\t(layer "User.4")\n\t)\n')
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(gr_rect((78.7, 41.0), (217.2, 160.7)), gr_rect((79.72, 153.17), (84.78, 159.65))))
    assert not any("pillar boss" in m for m in check(p))


def test_sheets_bp101(tmp_path):
    from check_full1590xx import _netlist_pins
    from gen_full1590xx import build_sheets
    uuid = build_sheets(tmp_path)
    proj = tmp_path / "fx-Full1590XX"
    pins = _netlist_pins(proj)
    assert pins[("BP101", "P1")] == "+9V"
    assert pins[("BP101", "P4")] == "+9VA"
    assert not {ref for ref, _ in pins} & {"D101", "R101", "L101", "C101"}
    assert f'(uuid "{uuid}")' in (proj / "board_setup.kicad_sch").read_text()
    assert '(title "1590XX Full Board Setup")' in (proj / "fx-Full1590XX.kicad_sch").read_text()


def test_led_body_centre(tmp_path):
    # D102 origin (pad 1) placed on the body centre: the body centre is then 1.27 mm off
    cx, cy, rot, layer = geometry.FOOTPRINTS["D102"]
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("D102", "LED_THT:LED_D5.0mm", layer, cx, cy, rot, [("1", 0, 0), ("2", 2.54, 0)])))
    assert any("D102 body centre" in m for m in check(p))


def test_board_stage_passes_check(tmp_path):
    # the whole build: sheets, then the board under KiCad's python, then the outline heal; the checker must pass and
    # the fleet's outline audit must find nothing left to heal (fx-L7's top edge has a collinear pair)
    import subprocess
    from gen_full1590xx import FLEET, PROJECT, build_board, build_sheets
    uuid = build_sheets(tmp_path)
    assert build_board(tmp_path, uuid) == []
    pcb = (tmp_path / PROJECT / f"{PROJECT}.kicad_pcb").read_text()
    assert '(title "1590XX Full Board Setup")' in pcb
    assert "125B" not in pcb            # neither Full125's title nor L7's leftover 125B screw dimensions and labels
    out = subprocess.run(["uv", "run", "pedal-fleet", "outline", "--no-process-check", str(tmp_path / PROJECT)],
                         cwd=FLEET, capture_output=True, text=True).stdout
    assert "clean; closes exactly" in out


def test_zone_fill_outside_outline(tmp_path):
    # a GND pour still carrying Full125's 125B fill (down to y 142.5) past the 1590XX bottom edge at y 135
    zone = ('\t(zone\n\t\t(net "GND")\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(filled_polygon\n\t\t\t(layer "F.Cu")\n'
            '\t\t\t(pts\n\t\t\t\t(xy 81.5 43.5) (xy 138.5 43.5) (xy 138.5 142.5) (xy 81.5 142.5)\n\t\t\t)\n\t\t)\n\t)\n')
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(zone))
    assert any("zone fill outside the outline" in m for m in check(p))
