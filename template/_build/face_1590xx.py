"""Build a 1590XX faceplate project and its Tayda drill list from a main board (KiCad python, pcbnew).

usage: face_1590xx.py BOARD OUT_DIR NAME --title TEXT [--supply TEXT] --frame REFS [--frame REFS ...]
                      [--report JSON] [--force]

Spec: ~/Claude/docs/superpowers/specs/2026-11-21-revolver-faceplate-design.md. Starts from the 1590XX faceplate
template (pedalfx/template/1950XXFacePlate) and, from the board's own parts:
- drills a hole (Edge.Cuts r 4.0) on every 16MM_B.MOUNT pot shaft (the drills follow the pots, Andy's 1590XX rule);
- labels each pot with its Control field 12.25 mm below the hole, in the template's CONTROL text style. A label that
  would come within 0.75 mm of its frame or a hole breaks onto two full-size lines centred on the label row (Andy's
  fallback); only if that still crowds does it narrow its characters, down to 1.8 mm;
- draws an exposed-copper (F.Mask) frame around each --frame group, stepped to the rows it occupies;
- keeps a glow-through LED trefoil only where the board has a through-hole LED, and writes footswitch and LED lines
  for those spots only;
- sets the title and supply text, refills the copper, saves, writes NAME-tayda-drill.txt and checks the result.
It refuses to overwrite an existing faceplate without --force, and always refuses one that is open in KiCad. It
stops on panel parts it does not know (toggles, other pot footprints) and on pots outside rows 1-2.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import faceplate as F  # noqa: E402
import geometry as G  # noqa: E402
from check_face1590xx import (HOLE_R, LABEL_CLEAR, _box_circle_gap, _box_in_poly, board_leds, board_pots,  # noqa: E402
                              board_unsupported, check_face)
from fix_face1590xx import NM, is_circle, mm, v  # noqa: E402

TEMPLATE_DIR, TEMPLATE = HERE.parent / "1950XXFacePlate", "1950XXFacePlate"
MIN_CHAR_W = 1.8            # Andy's call to make: 'BOOST GAIN' needs ~1.85 mm to fit 18.5 mm (2026-11-21 ruling)


def copy_project(out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".kicad_sch", ".kicad_dru"):
        shutil.copy(TEMPLATE_DIR / (TEMPLATE + ext), out_dir / (name + ext))
    pro = json.loads((TEMPLATE_DIR / (TEMPLATE + ".kicad_pro")).read_text())
    pro.setdefault("meta", {})["filename"] = name + ".kicad_pro"
    (out_dir / (name + ".kicad_pro")).write_text(json.dumps(pro, indent=2) + "\n")
    shutil.copy(TEMPLATE_DIR / ".gitignore", out_dir / ".gitignore")


def frame_poly(group):
    """The stepped outline around a group of pots, drawn on the template grid (faceplate.frame_for)."""
    return F.frame_for([(F.face_x(sx), sy) for _ref, _ctl, sx, sy in group])


def draw_frame(board, poly) -> None:
    for item in F.fillet(poly, F.FRAME_R):
        s = pcbnew.PCB_SHAPE(board)
        s.SetLayer(pcbnew.F_Mask)
        s.SetWidth(int(F.FRAME_W * NM))
        if item[0] == "line":
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(v(*item[1]))
            s.SetEnd(v(*item[2]))
        else:
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetArcGeometry(v(*item[1]), v(*item[2]), v(*item[3]))
        board.Add(s)


def set_holes(board, holes) -> None:
    old = [d for d in board.GetDrawings() if is_circle(d, pcbnew.Edge_Cuts, HOLE_R)]
    width = old[0].GetWidth()
    for d in old:
        board.Delete(d)
    for x, y in holes:
        c = pcbnew.PCB_SHAPE(board)
        c.SetShape(pcbnew.SHAPE_T_CIRCLE)
        c.SetLayer(pcbnew.Edge_Cuts)
        c.SetStart(v(x, y))
        c.SetEnd(v(x + HOLE_R, y))
        c.SetWidth(width)
        board.Add(c)


def box(t):
    b = t.GetBoundingBox()
    return (b.GetLeft() / NM, b.GetTop() / NM, b.GetRight() / NM, b.GetBottom() / NM)


def fits(t, poly, holes) -> bool:
    b = box(t)
    return (poly is None or _box_in_poly(b, poly, LABEL_CLEAR)) and all(
        _box_circle_gap(b, h, HOLE_R) >= LABEL_CLEAR for h in holes)


def place_labels(board, pots, poly_of, holes):
    """Fill the CONTROL placeholders, nearest first; return the labels whose characters had to be narrowed."""
    spare = [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() == "CONTROL"]
    narrowed = []
    for ref, ctl, sx, sy in sorted(pots, key=lambda p: (p[3], F.face_x(p[2]))):
        at = (F.face_x(sx), sy + F.LABEL_DY)
        t = min(spare, key=lambda d: math.hypot(mm(d.GetPosition())[0] - at[0], mm(d.GetPosition())[1] - at[1]))
        spare.remove(t)
        t.SetText(ctl)
        t.SetPosition(v(*at))
        full = t.GetTextWidth()
        if not fits(t, poly_of.get(ref), holes) and " " in ctl:
            # Andy's fallback (face-Revolver, 2026-11-21): two full-size lines, centred on the label row
            t.SetText(ctl.replace(" ", "\n", 1))
            t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
            narrowed.append((ref, ctl, "two lines"))
        while not fits(t, poly_of.get(ref), holes):
            w = round(t.GetTextWidth() / NM - 0.1, 2)
            if w < MIN_CHAR_W - 1e-9:
                sys.exit(f"label {ctl!r} ({ref}) does not fit even at {MIN_CHAR_W} mm characters")
            t.SetTextWidth(int(round(w * NM)))
        if t.GetTextWidth() != full:
            narrowed.append((ref, ctl, "%.2f mm characters" % (t.GetTextWidth() / NM)))
    for d in spare:
        board.Delete(d)
    return narrowed


def led_spots(board_text):
    """The template LED spots (face x, y) that have a through-hole LED behind them on the board. An LED anywhere
    else stops the build: the template has a glow-through trefoil only at its three spots."""
    spots = []
    for ref, bx, by in board_leds(board_text):
        face = (F.face_x(bx), by)
        hit = [s for s in F.LED_FACE if math.hypot(s[0] - face[0], s[1] - face[1]) <= 0.2]
        if not hit:
            sys.exit(f"LED {ref} at board ({bx:.2f}, {by:.2f}) is not on a template LED spot "
                     f"(board x {[F.FACE_MIRROR - s[0] for s in F.LED_FACE]}, y {F.LED_FACE[0][1]})")
        spots.append(hit[0])
    return sorted(set(spots))


def trefoil_parts(board, centre):
    """The nine items of the glow-through trefoil at a face spot: four F.Cu keepouts, three F.Mask leaves, the
    F.Mask centre dot and the B.Mask window."""
    near = lambda item: math.hypot(*(a - b for a, b in zip(mm(item.GetBoundingBox().Centre()), centre))) <= 4.0
    parts = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetLayer() == pcbnew.F_Cu and near(z)]
    parts += [d for d in board.GetDrawings() if d.GetClass() == "PCB_SHAPE" and near(d)
              and (d.GetLayer() == pcbnew.F_Mask or is_circle(d, pcbnew.B_Mask, 3.5))]
    if len(parts) != 9:
        sys.exit(f"expected 9 trefoil parts at {centre}, found {len(parts)}")
    return parts


def set_text(board, old: str, new: str) -> None:
    hits = [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() == old]
    if len(hits) != 1:
        sys.exit(f"expected one {old!r} text in the template, found {len(hits)}")
    hits[0].SetText(new)


def measured_labels(pcb_path: Path, pots):
    """(text, x0, y0, x1, y1) of each pot's label on the SAVED board, found by position (texts repeat)."""
    saved = pcbnew.LoadBoard(str(pcb_path))
    texts = [d for d in saved.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS]
    out = []
    for _ref, ctl, sx, sy in pots:
        at = (F.face_x(sx), sy + F.LABEL_DY)
        t = min(texts, key=lambda d: math.hypot(mm(d.GetPosition())[0] - at[0], mm(d.GetPosition())[1] - at[1]))
        out.append([t.GetText(), *box(t)])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("out_dir")
    ap.add_argument("name")
    ap.add_argument("--title", required=True)
    ap.add_argument("--supply", default=None)
    ap.add_argument("--frame", action="append", default=[], help="comma-separated pot refs drawn inside one frame")
    ap.add_argument("--report", default=None)
    ap.add_argument("--force", action="store_true", help="overwrite an existing faceplate (never one open in KiCad)")
    a = ap.parse_args()

    out_dir = Path(a.out_dir)
    pcb = out_dir / (a.name + ".kicad_pcb")
    if any((out_dir / f"~{a.name}{ext}.lck").exists() for ext in (".kicad_pcb", ".kicad_pro")):
        sys.exit(f"{out_dir} is open in KiCad (lock file present); close it first")
    if pcb.exists() and not a.force:
        sys.exit(f"{pcb} exists and may hold hand edits; pass --force to overwrite it")

    board_text = Path(a.board).read_text()
    unknown = board_unsupported(board_text)
    if unknown:
        sys.exit("unsupported panel part(s), no faceplate hole or Tayda line for: "
                 + ", ".join(f"{r} ({lib})" for r, lib in unknown))
    pots = board_pots(board_text)
    off_row = [(r, sy) for r, _c, _x, sy in pots if min(abs(sy - row) for row in F.ROWS) > 0.5]
    if off_row:
        sys.exit("pot shaft(s) not on row 1 or 2 (row 3 is not supported): "
                 + ", ".join(f"{r} at y {y:.2f}" for r, y in off_row))
    leds = led_spots(board_text)
    by_ref = {p[0]: p for p in pots}
    groups = [[by_ref[r.strip()] for r in g.split(",")] for g in a.frame]
    polys = [frame_poly(g) for g in groups]
    poly_of = {p[0]: poly for g, poly in zip(groups, polys) for p in g}
    holes = [(F.face_x(sx), sy) for _r, _c, sx, sy in pots]

    copy_project(out_dir, a.name)
    board = pcbnew.LoadBoard(str(TEMPLATE_DIR / (TEMPLATE + ".kicad_pcb")))
    for spot in F.LED_FACE:
        if spot not in leds:
            for part in trefoil_parts(board, spot):
                board.Delete(part)
    set_holes(board, holes)
    narrowed = place_labels(board, pots, poly_of, holes)
    for poly in polys:
        draw_frame(board, poly)
    set_text(board, "PEDALNAME", a.title)
    if a.supply:
        set_text(board, "9 VDC", a.supply)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(str(pcb))

    drill = out_dir / (a.name + "-tayda-drill.txt")
    feet = sorted(round(G.CENTRE[0] - (F.FACE_MIRROR - x), 4) for x, _y in leds)     # Tayda Y under each LED
    drill.write_text("\n".join(F.tayda_lines([(sx, sy) for _r, _c, sx, sy in pots], feet)) + "\n")

    labels = measured_labels(pcb, pots)
    msgs = check_face(pcb.read_text(), holes, leds, labels=labels, frames=polys)
    if a.report:
        Path(a.report).write_text(json.dumps({"pots": pots, "labels": labels, "frames": polys, "holes": holes}))
    for ref, ctl, how in narrowed:
        print(f"label {ref} {ctl!r} did not fit on one full-size line: {how}")
    for m in msgs:
        print("FAIL", m)
    print("wrote", pcb, "and", drill, "-", "PASS" if not msgs else f"{len(msgs)} failure(s)")
    sys.exit(1 if msgs else 0)


if __name__ == "__main__":
    main()
