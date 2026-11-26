import math
import random

import pytest

from pedalfleet import cli, silklabels
from tests.helpers import write_project

UUID = '(uuid "00000000-0000-0000-0000-000000000000")'


def footprint(ref, x, y, rot, label_at, lib="Resistor_SMD:R_0603_1608Metric", half=(1.48, 0.73),
              pad_x=0.775, pad_size=(0.9, 0.95), npads=2, layer="F.Cu", extra=""):
    lx, ly, la = label_at
    pads = "".join(
        f'\t\t(pad "{n + 1}" smd roundrect\n\t\t\t(at {(-pad_x if n == 0 else pad_x) if npads == 2 else n} 0 {rot})\n'
        f'\t\t\t(size {pad_size[0]} {pad_size[1]})\n\t\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n\t\t\t{UUID}\n\t\t)\n'
        for n in range(npads))
    return (f'\t(footprint "{lib}"\n\t\t(layer "{layer}")\n\t\t{UUID}\n\t\t(at {x} {y} {rot})\n'
            f'\t\t(property "Reference" "{ref}"\n\t\t\t(at {lx} {ly} {la})\n\t\t\t(layer "F.SilkS")\n\t\t\t{UUID}\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 0.8 0.8)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(fp_rect\n\t\t\t(start {-half[0]} {-half[1]})\n\t\t\t(end {half[0]} {half[1]})\n'
            f'\t\t\t(stroke\n\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(fill no)\n'
            f'\t\t\t(layer "F.CrtYd")\n\t\t\t{UUID}\n\t\t)\n{extra}{pads}\t)\n')


def silk_line(x1, y1, x2, y2, width=0.12):
    return (f'\t\t(fp_line\n\t\t\t(start {x1} {y1})\n\t\t\t(end {x2} {y2})\n'
            f'\t\t\t(stroke\n\t\t\t\t(width {width})\n\t\t\t\t(type solid)\n\t\t\t)\n'
            f'\t\t\t(layer "F.SilkS")\n\t\t\t{UUID}\n\t\t)\n')


def silk_text(text, x, y, angle=0, size=1.0, kind="fp_text user", layer="F.SilkS", hide=False):
    hidden = "\t\t\t(hide yes)\n" if hide else ""
    return (f'\t\t({kind} "{text}"\n\t\t\t(at {x} {y} {angle})\n\t\t\t(layer "{layer}")\n{hidden}'
            f'\t\t\t{UUID}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {size} {size})\n'
            f'\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')


def board(*footprints, outline=(0, 0, 60, 40)):
    edge = (f'\t(gr_rect\n\t\t(start {outline[0]} {outline[1]})\n\t\t(end {outline[2]} {outline[3]})\n'
            f'\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type default)\n\t\t)\n\t\t(fill no)\n'
            f'\t\t(layer "Edge.Cuts")\n\t\t{UUID}\n\t)\n')
    return '(kicad_pcb\n\t(version 20250114)\n\t(generator "pcbnew")\n' + "".join(footprints) + edge + ")\n"


def plan_for(text):
    fps = silklabels.parse_footprints(text)
    return fps, silklabels.plan_labels(fps, silklabels.board_outline(text))


def label_at(text, ref):
    fp = next(f for f in silklabels.parse_footprints(text) if f.ref == ref)
    return fp.label["lx"], fp.label["ly"], fp.label["angle"]


def test_transform_round_trip():
    rng = random.Random(1)
    for _ in range(200):
        fx, fy, rot, lx, ly = (rng.uniform(-100, 100) for _ in range(5))
        bx, by = silklabels.to_board(fx, fy, rot, lx, ly)
        assert silklabels.to_local(fx, fy, rot, bx, by) == pytest.approx((lx, ly), abs=1e-9)


def test_rotation_convention_matches_kicad():
    # a footprint at 180 degrees with its label at local +y draws the label north (smaller board y)
    assert silklabels.to_board(10, 10, 180, 0, 1.5) == pytest.approx((10, 8.5))
    # at 90 degrees, local -x maps to board +y (south) and local +y to board +x (east)
    assert silklabels.to_board(0, 0, 90, 0, 1) == pytest.approx((1, 0))


def test_south_label_moves_north_and_only_that_line_changes():
    text = board(footprint("R1", 20, 20, 0, (0, 1.43, 0)))
    fps, plans = plan_for(text)
    assert plans["R1"].action == "move"
    new = silklabels.rewrite(text, fps, plans)
    assert label_at(new, "R1") == pytest.approx((0, -1.15, 0))
    changed = [(a, b) for a, b in zip(text.splitlines(), new.splitlines()) if a != b]
    assert changed == [("\t\t\t(at 0 1.43 0)", "\t\t\t(at 0 -1.15 0)")]


def test_label_already_north_is_kept_including_hand_tuned_gaps():
    # rotated 180 with the label at local +y: board north, 0.52 mm out (closer than the default 0.7)
    text = board(footprint("R2", 20, 20, 180, (0, 1.25, 180)))
    fps, plans = plan_for(text)
    assert plans["R2"].action == "keep"
    assert silklabels.rewrite(text, fps, plans) == text


def test_vertical_part_label_moves_west_reading_bottom_to_top():
    text = board(footprint("C1", 20, 20, 90, (0, 1.68, 90), lib="Capacitor_SMD:C_0805_2012Metric",
                           half=(1.7, 0.98), pad_x=0.95, pad_size=(1.0, 1.45)))
    fps, plans = plan_for(text)
    assert plans["C1"].action == "move"
    new = silklabels.rewrite(text, fps, plans)
    lx, ly, angle = label_at(new, "C1")
    assert angle == 90
    bx, by = silklabels.to_board(20, 20, 90, lx, ly)
    # the turned pads reach 0.725 mm west of centre; the label edge sits 0.20 mm beyond them
    assert (bx, by) == pytest.approx((20 - 0.725 - 0.20 - 0.475, 20))


def test_own_silk_outline_sets_the_spacing():
    # silk lines 0.8 mm out (0.12 wide) reach past the pads, so the label clears the silk instead
    text = board(footprint("R8", 20, 20, 0, (0, 2.5, 0), extra=silk_line(-0.3, -0.8, 0.3, -0.8) + silk_line(-0.3, 0.8, 0.3, 0.8)))
    fps, plans = plan_for(text)
    new = silklabels.rewrite(text, fps, plans)
    assert label_at(new, "R8") == pytest.approx((0, -(0.86 + 0.20 + 0.475), 0))


def test_label_may_overlap_its_own_courtyard():
    # a roomy courtyard (1.2 mm half-height) no longer pushes the label out: it sits 0.20 mm past the pads
    text = board(footprint("R9", 20, 20, 0, (0, 2.5, 0), half=(1.6, 1.2)))
    fps, plans = plan_for(text)
    assert plans["R9"].action == "move"
    assert label_at(silklabels.rewrite(text, fps, plans), "R9") == pytest.approx((0, -1.15, 0))


@pytest.mark.parametrize("edge_gap,action", [(0.05, "keep"), (-0.02, "keep"), (0.75, "keep"),
                                              (-0.2, "move"), (1.0, "move")])
def test_fit_window_is_measured_from_the_pads_and_silk(edge_gap, action):
    # Andy packs labels 0.05-0.35 mm off the part's own silk and pads, some touching it; those stay put
    centre = -(0.475 + edge_gap + 0.475)
    text = board(footprint("R10", 20, 20, 0, (0, round(centre, 4), 0)))
    _, plans = plan_for(text)
    assert plans["R10"].action == action


def test_a_neighbours_silk_caption_blocks_a_move():
    # pot captions (${Control}) may overlap other silk under the fleet DRC rules, so the planner checks them itself
    pot = footprint("RV6", 20, 10, 0, (0, -3, 0), lib="_MB_potentiometers:16MM", npads=3, half=(5, 0.5),
                    pad_size=(0.3, 0.3), extra=silk_text("${Control}", 0, 8.6)
                    + silk_text("LEVEL", 0, 5, kind='property "Control"', layer="F.Fab", hide=True))
    text = board(footprint("R11", 20, 20, 0, (0, 1.43, 0)), pot)
    _, plans = plan_for(text)
    assert plans["R11"].action == "blocked" and plans["R11"].reason == "text of RV6"


def test_a_neighbours_silk_line_blocks_a_move():
    other = footprint("J5", 30, 30, 0, (0, -1.43, 0), extra=silk_line(-10.4, -11.15, -9.6, -11.15))
    text = board(footprint("R12", 20, 20, 0, (0, 1.43, 0)), other)
    _, plans = plan_for(text)
    assert plans["R12"].action == "blocked" and plans["R12"].reason == "silk of J5"


def test_neighbour_pad_blocks_a_move_and_names_the_neighbour():
    text = board(footprint("R3", 20, 20, 0, (0, 1.43, 0)),      # label south, wants north
                 footprint("R4", 20, 18.4, 0, (0, -1.43, 0)))   # sits right where R3's label would go
    _, plans = plan_for(text)
    assert plans["R3"].action == "blocked" and "R4" in plans["R3"].reason
    assert plans["R4"].action == "keep"


def test_board_edge_blocks_a_move():
    text = board(footprint("R5", 20, 1.2, 0, (0, 1.43, 0)))
    _, plans = plan_for(text)
    assert plans["R5"].action == "blocked" and plans["R5"].reason == "board edge"


def test_only_two_pad_front_passives_and_diodes_are_targets():
    text = board(footprint("U1", 30, 30, 0, (0, 3, 0), lib="Package_SO:SOIC-8", npads=8, half=(3.7, 2.7)),
                 footprint("C9", 40, 20, 0, (0, 4, 0), lib="Capacitor_SMD:CP_Elec_6.3x5.4", half=(3.4, 3.4)),
                 footprint("R6", 10, 30, 0, (0, 1.43, 0), layer="B.Cu"),
                 footprint("D1", 50, 30, 0, (0, 1.6, 0), lib="Diode_SMD:D_SOD-323F", half=(1.6, 0.85)))
    _, plans = plan_for(text)
    assert set(plans) == {"D1"} and plans["D1"].action == "move"


def test_skip_leaves_named_refs_alone():
    text = board(footprint("R7", 20, 20, 0, (0, 1.43, 0)))
    fps = silklabels.parse_footprints(text)
    plans = silklabels.plan_labels(fps, silklabels.board_outline(text), skip={"R7"})
    assert plans["R7"].action == "skip"


def test_drc_cross_check_puts_back_a_move_that_adds_a_silk_violation(tmp_path):
    p = write_project(tmp_path / "fx-S", "fx-S")
    p.pcb.write_text(board(footprint("R1", 20, 20, 0, (0, 1.43, 0)), footprint("R2", 40, 20, 0, (0, 1.43, 0))))

    def fake_drc(kicad_cli, pcb, out_json):
        north = label_at(pcb.read_text(), "R1")[1] < 0
        items = [{"description": "Reference field of R1"}, {"description": "Segment of U9 on F.Silkscreen"}]
        return {"violations": [{"type": "silk_overlap", "items": items}] if north else []}

    result = silklabels.run(p.pcb, p.pro, kicad_cli=tmp_path / "kicad-cli", drc=fake_drc)
    assert result.plans["R1"].action == "blocked" and result.plans["R1"].reason == "DRC silk_overlap with U9"
    assert result.plans["R2"].action == "move"
    assert result.drc_checked and not result.new_violations
    assert label_at(result.text, "R1") == (0, 1.43, 0)


def test_cli_dry_run_then_write(tmp_path, capsys):
    p = write_project(tmp_path / "fx-S", "fx-S")
    original = board(footprint("R1", 20, 20, 0, (0, 1.43, 0)), footprint("R2", 20, 30, 180, (0, 1.25, 180)))
    p.pcb.write_text(original)
    code = cli.main(["silk-labels", str(p.dir), "--dry-run", "--no-drc", "--no-process-check"])
    out = capsys.readouterr().out
    assert code == 0 and "1 moved, 1 already fit, 0 left alone" in out and "nothing written (dry run)" in out
    assert p.pcb.read_text() == original
    code = cli.main(["silk-labels", str(p.dir), "--no-drc", "--no-process-check"])
    out = capsys.readouterr().out
    assert code == 0 and "wrote fx-S.kicad_pcb: 1 label(s) moved" in out
    assert label_at(p.pcb.read_text(), "R1") == pytest.approx((0, -1.15, 0))


def test_cli_refuses_while_kicad_has_the_board_open(tmp_path, capsys, monkeypatch):
    p = write_project(tmp_path / "fx-S", "fx-S")
    p.pcb.write_text(board(footprint("R1", 20, 20, 0, (0, 1.43, 0))))
    p.lock_files[0].write_text("{}")
    monkeypatch.setattr("pedalfleet.guard.process_commands",
                        lambda: ["/Applications/KiCad/KiCad.app/Contents/MacOS/pcbnew x.kicad_pcb"])
    code = cli.main(["silk-labels", str(p.dir), "--no-drc", "--force"])
    assert code == 1 and "not touched" in capsys.readouterr().out
    assert label_at(p.pcb.read_text(), "R1") == (0, 1.43, 0)


def test_angle_folds_keep_text_upright():
    assert math.isclose(silklabels.to_board(0, 0, -90, 0, -1.55)[0], 1.55)


# --- through-hole values -------------------------------------------------------------------------

FILM = "Capacitor_THT:C_Rect_L7.2mm_W2.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2"


def cap(ref, x, y, rot, value="22nF", attrs="through_hole", pitch=5, pad=1.6, lib=FILM, ref_at=None,
        value_at=None, value_layer="F.Fab", hide=False, font=1, extra="", smd=False):
    """A THT part laid out the way KiCad 10 saves one: pad 1 at the origin, pad 2 at (pitch, 0)."""
    rx, ry, ra = ref_at or (pitch / 2, -2.5, rot)
    vx, vy, va = value_at or (pitch / 2, 2.5, rot)
    hidden = "\t\t\t(hide yes)\n" if hide else ""
    attr = f"\t\t(attr {attrs})\n" if attrs else ""
    kind, drill = ("smd roundrect", "") if smd else ("thru_hole circle", "\t\t\t(drill 0.8)\n")
    pads = "".join(
        f'\t\t(pad "{n + 1}" {kind}\n\t\t\t(at {n * pitch} 0 {rot})\n\t\t\t(size {pad} {pad})\n'
        f'{drill}\t\t\t(layers "*.Cu" "*.Mask")\n\t\t\t{UUID}\n\t\t)\n' for n in range(2))
    return (f'\t(footprint "{lib}"\n\t\t(layer "F.Cu")\n\t\t{UUID}\n\t\t(at {x} {y} {rot})\n'
            f'\t\t(property "Reference" "{ref}"\n\t\t\t(at {rx} {ry} {ra})\n\t\t\t(layer "F.SilkS")\n\t\t\t{UUID}\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 0.8 0.8)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(property "Value" "{value}"\n\t\t\t(at {vx} {vy} {va})\n\t\t\t(layer "{value_layer}")\n{hidden}'
            f'\t\t\t{UUID}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {font} {font})\n'
            f'\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'{attr}{extra}{pads}\t)\n')


def value_plans_for(text, **kwargs):
    fps = silklabels.parse_footprints(text)
    outline = silklabels.board_outline(text)
    labels = silklabels.plan_labels(fps, outline)
    return fps, labels, silklabels.plan_values(fps, outline, labels, **kwargs)


def value_at(text, ref):
    fp = next(f for f in silklabels.parse_footprints(text) if f.ref == ref)
    v = fp.value
    return v["lx"], v["ly"], v["angle"], v["layer"], v["hidden"], v["size"]


def test_horizontal_film_cap_value_is_centred_between_its_leads():
    text = board(cap("C1", 20, 20, 0, hide=True))
    fps, labels, values = value_plans_for(text)
    assert values["C1"].action == "place"
    new = silklabels.rewrite(text, fps, labels, values)
    assert value_at(new, "C1") == (2.5, 0, 0, "F.SilkS", False, 0.8)
    assert silklabels.to_board(20, 20, 0, 2.5, 0) == pytest.approx((22.5, 20))


@pytest.mark.parametrize("rot,angle", [(90, 90), (270, 90), (180, 0), (-90, 90)])
def test_value_reads_along_the_part_and_upright(rot, angle):
    text = board(cap("C2", 20, 20, rot))
    fps, labels, values = value_plans_for(text)
    assert values["C2"].action == "place"
    lx, ly, a, layer, hidden, size = value_at(silklabels.rewrite(text, fps, labels, values), "C2")
    assert (lx, ly, a) == (2.5, 0, angle)
    # the value's board position is the midpoint of the two pad centres
    p1, p2 = silklabels.to_board(20, 20, rot, 0, 0), silklabels.to_board(20, 20, rot, 5, 0)
    assert silklabels.to_board(20, 20, rot, lx, ly) == pytest.approx(((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2))


def test_value_rewrite_touches_only_at_layer_hide_and_font():
    text = board(footprint("R1", 40, 20, 0, (0, -1.15, 0)), cap("C3", 20, 20, 90, hide=True))
    fps, labels, values = value_plans_for(text)
    new = silklabels.rewrite(text, fps, labels, values)
    assert new == board(footprint("R1", 40, 20, 0, (0, -1.15, 0)),
                        cap("C3", 20, 20, 90, value_at=(2.5, 0, 90), value_layer="F.SilkS", font=0.8))


def test_radial_can_on_a_tight_pitch_is_reported_not_printed_over_its_pads():
    text = board(cap("C4", 20, 20, 0, value="100uF", pitch=2.5, lib="Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"))
    fps, labels, values = value_plans_for(text)
    assert values["C4"].action == "blocked" and values["C4"].reason.startswith("too tight")
    assert silklabels.rewrite(text, fps, labels, values) == text


def test_smd_part_is_left_alone():
    # an SMD cap Andy fits by hand (1206 pads 3 mm apart) still gets no value: the rule is through-hole only
    text = board(cap("C5", 20, 20, 0, value="10u", attrs="smd exclude_from_pos_files exclude_from_bom dnp",
                     pitch=3, pad=1, smd=True, lib="Capacitor_SMD:C_1206_3216Metric"))
    fps, labels, values = value_plans_for(text)
    assert values == {}
    assert value_at(silklabels.rewrite(text, fps, labels, values), "C5") == value_at(text, "C5")


@pytest.mark.parametrize("attrs", ["through_hole", "through_hole exclude_from_bom dnp", "exclude_from_bom", ""])
def test_through_hole_comes_from_the_attr_or_the_drilled_pads(attrs):
    # JLC-fitted films get the value as well as hand-fit ones; an attr without through_hole falls back to the pads
    _, _, values = value_plans_for(board(cap("C7", 20, 20, 0, attrs=attrs)))
    assert values["C7"].action == "place"


@pytest.mark.parametrize("ref,value,lib,pitch", [
    ("R1", "10k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 10.16),
    ("D1", "1N4148", "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal", 7.62),
    ("L1", "100u", "Inductor_THT:L_Axial_L5.3mm_D2.2mm_P10.16mm_Horizontal_Vishay_IM-1", 10.16)])
def test_through_hole_resistors_diodes_and_inductors_get_their_value(ref, value, lib, pitch):
    _, _, values = value_plans_for(board(cap(ref, 20, 20, 0, value=value, lib=lib, pitch=pitch)))
    assert values[ref].action == "place"


@pytest.mark.parametrize("ref,lib", [("D2", "LED_THT:LED_D3.0mm"), ("RV1", "_MB_potentiometers:TRIM"),
                                     ("SW1", "Button_Switch_THT:SW_PUSH"), ("J1", "Connector:Jack")])
def test_hand_managed_parts_are_left_alone(ref, lib):
    # LEDs (D refs on LED footprints), pots, switches and jacks keep their own captions
    _, _, values = value_plans_for(board(cap(ref, 20, 20, 0, value="x", lib=lib)))
    assert values == {}


def test_value_marked_dnp_is_not_fitted_and_is_left_alone():
    _, _, values = value_plans_for(board(cap("C9", 20, 20, 0, value="100n (DNP)", attrs="through_hole dnp")))
    assert values["C9"].action == "skip" and "DNP" in values["C9"].reason


@pytest.mark.parametrize("at,font,action", [((2.5, 0, 90), 0.8, "keep"),
                                            ((2.5, -0.16, 90), 0.8, "keep"),   # hand-placed, fx-Nashville C6
                                            ((2.45, 0.25, 90), 0.8, "keep"),
                                            ((2.25, 0, 90), 0.8, "place"),     # crowds pad 1
                                            ((2.5, 0.5, 90), 0.8, "place"),
                                            ((2.5, 0, 0), 0.8, "place"),       # reads across the part
                                            ((2.5, 0, 90), 1, "place")])       # wrong size
def test_value_already_centred_is_kept_including_hand_placements(at, font, action):
    text = board(cap("C10", 20, 20, 90, value_at=at, value_layer="F.SilkS", font=font))
    fps, labels, values = value_plans_for(text)
    assert values["C10"].action == action
    assert (silklabels.rewrite(text, fps, labels, values) == text) == (action == "keep")


def test_own_reference_between_the_leads_blocks_the_value():
    _, _, values = value_plans_for(board(cap("C11", 20, 20, 0, ref_at=(2.5, 0, 0))))
    assert values["C11"].action == "blocked" and values["C11"].reason == "label of C11"


def test_skip_also_leaves_the_value_alone():
    _, _, values = value_plans_for(board(cap("C12", 20, 20, 0)), skip={"C12"})
    assert values["C12"].action == "skip"


def test_value_field_violations_are_told_apart_from_reference_ones():
    report = {"violations": [{"type": "silk_overlap", "items": [{"description": "Value field of C1 (22nF)"},
                                                                {"description": "Reference field of R1"}]}]}
    assert silklabels.silk_violations(report) == {("silk_overlap", ("C1 value", "R1"))}


def test_a_board_item_in_a_violation_keeps_its_description():
    # fx-WahWahWah: C27's value ran into a board-level silk note, which no footprint owns
    report = {"violations": [{"type": "silk_overlap", "items": [{"description": "Value field of C27 (2.2u)"},
                                                                {"description": "PCB text '2 x 2.2u Film\n' on F.Silkscreen"}]}]}
    assert silklabels.silk_violations(report) == {("silk_overlap", ("C27 value", "PCB text '2 x 2.2u Film ' on F.Silkscreen"))}


def test_drc_cross_check_puts_back_a_value_that_adds_a_silk_violation(tmp_path):
    p = write_project(tmp_path / "fx-S", "fx-S")
    p.pcb.write_text(board(cap("C1", 20, 20, 0), cap("C2", 40, 20, 0)))

    def fake_drc(kicad_cli, pcb, out_json):
        centred = value_at(pcb.read_text(), "C1")[1] == 0
        items = [{"description": "Value field of C1 (22nF)"}, {"description": "Segment of U9 on F.Silkscreen"}]
        return {"violations": [{"type": "silk_overlap", "items": items}] if centred else []}

    result = silklabels.run(p.pcb, p.pro, kicad_cli=tmp_path / "kicad-cli", drc=fake_drc)
    assert result.values["C1"].action == "blocked" and result.values["C1"].reason == "DRC silk_overlap with U9"
    assert result.values["C2"].action == "place"
    assert value_at(result.text, "C1")[:4] == (2.5, 2.5, 0, "F.Fab")


def test_cli_reports_and_places_values_by_default(tmp_path, capsys):
    p = write_project(tmp_path / "fx-S", "fx-S")
    original = board(cap("C1", 20, 20, 0), cap("C4", 40, 20, 0, value="100uF", pitch=2.5))
    p.pcb.write_text(original)
    code = cli.main(["silk-labels", str(p.dir), "--dry-run", "--no-drc", "--no-process-check"])
    out = capsys.readouterr().out
    assert code == 0 and "through-hole values: 1 placed, 0 already centred, 1 left alone" in out
    assert "C1     22nF" in out and "C4     100uF  too tight" in out and "nothing written (dry run)" in out
    assert p.pcb.read_text() == original
    code = cli.main(["silk-labels", str(p.dir), "--no-drc", "--no-process-check"])
    out = capsys.readouterr().out
    assert code == 0 and "wrote fx-S.kicad_pcb: 0 label(s) moved, 1 value(s) placed" in out
    assert value_at(p.pcb.read_text(), "C1")[:4] == (2.5, 0, 0, "F.SilkS")


def test_cli_no_values_leaves_values_alone(tmp_path, capsys):
    p = write_project(tmp_path / "fx-S", "fx-S")
    original = board(cap("C1", 20, 20, 0))
    p.pcb.write_text(original)
    code = cli.main(["silk-labels", str(p.dir), "--no-values", "--no-drc", "--no-process-check"])
    out = capsys.readouterr().out
    assert code == 0 and "values" not in out and p.pcb.read_text() == original


# --- library use (kicad-live labels) ------------------------------------------------------------


def test_footprint_uuid_is_parsed():
    text = board(footprint("R1", 20, 20, 0, (0, 1.43, 0)).replace(UUID, '(uuid "fp-r1")', 1))
    assert silklabels.parse_footprints(text)[0].uuid == "fp-r1"


def test_only_limits_the_parts_planned_and_keeps_the_rest_as_obstacles():
    # R2's label sits where R1's would go; with R2 out of scope it stays put and blocks R1
    text = board(footprint("R1", 20, 20, 0, (0, 1.43, 0)), footprint("R2", 30, 20, 0, (-10, -1.15, 0)),
                 cap("C1", 40, 10, 0), cap("C2", 40, 30, 0))
    fps = silklabels.parse_footprints(text)
    outline = silklabels.board_outline(text)
    labels = silklabels.plan_labels(fps, outline, only={"R1", "C1"})
    assert set(labels) == {"R1"} and labels["R1"].reason == "label of R2"
    values = silklabels.plan_values(fps, outline, labels, only={"R1", "C1"})
    assert set(values) == {"C1"}


def test_run_passes_only_through_and_returns_the_footprints(tmp_path):
    p = write_project(tmp_path / "fx-S", "fx-S")
    p.pcb.write_text(board(footprint("R1", 20, 20, 0, (0, 1.43, 0)), cap("C1", 40, 10, 0)))
    result = silklabels.run(p.pcb, p.pro, only={"C1"})
    assert result.plans == {} and set(result.values) == {"C1"}
    assert [fp.ref for fp in result.footprints] == ["R1", "C1"]


def test_drc_cross_check_uses_the_projects_rules_file(tmp_path):
    p = write_project(tmp_path / "fx-S", "fx-S")
    p.pcb.write_text(board(footprint("R1", 20, 20, 0, (0, 1.43, 0))))
    p.pcb.with_suffix(".kicad_dru").write_text("(version 1)\n")
    seen = []

    def fake_drc(kicad_cli, pcb, out_json):
        seen.append(pcb.with_suffix(".kicad_dru").read_text())
        return {"violations": []}

    silklabels.run(p.pcb, p.pro, kicad_cli=tmp_path / "kicad-cli", drc=fake_drc)
    assert seen and all(rules == "(version 1)\n" for rules in seen)


def test_report_lines_match_the_cli_report():
    text = board(footprint("R1", 20, 20, 0, (0, 1.43, 0)), cap("C1", 40, 10, 0),
                 cap("C4", 40, 30, 0, value="100uF", pitch=2.5))
    fps = silklabels.parse_footprints(text)
    outline = silklabels.board_outline(text)
    labels = silklabels.plan_labels(fps, outline)
    result = silklabels.Result(labels, text, values=silklabels.plan_values(fps, outline, labels))
    lines = silklabels.report_lines(result, "fx-S")
    assert lines[0] == "== fx-S: 1 passive/diode label(s): 1 moved, 0 already fit, 0 left alone"
    assert "   through-hole values: 1 placed, 0 already centred, 1 left alone" in lines
    assert any(line.startswith("     C4     100uF  too tight") for line in lines)
