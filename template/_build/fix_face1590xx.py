"""One-shot fix: bring the 1590XX faceplate template in line with Full1590XXTemplate (KiCad python, pcbnew).

usage: fix_face1590xx.py FACEPLATE.kicad_pcb BOARD_TEMPLATE.kicad_pcb      (rewrites FACEPLATE in place)

Spec: ~/Claude/docs/superpowers/specs/2026-11-21-revolver-faceplate-design.md. It:
- puts the 12 pot holes (Edge.Cuts r 4.0) exactly on faceplate.TEMPLATE_HOLES and the CONTROL placeholders 12.25 mm
  below them;
- replaces the template's one glow-through LED trefoil (four F.Cu keepouts, three F.Mask leaves, an F.Mask dot and a
  B.Mask window, centred on faceplate.TREFOIL_SRC) with a copy at each faceplate.LED_FACE spot;
- swaps the guide layers User.2/3/4 (125B guides) for the board template's own, mirrored into face coordinates
  (x -> 298 - x), text kept readable;
- refills the copper and saves.
"""
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import faceplate as F  # noqa: E402

NM = 1_000_000
GUIDE_LAYERS = (pcbnew.User_2, pcbnew.User_3, pcbnew.User_4)
TITLE = "1590XX Faceplate"


def v(x, y):
    return pcbnew.VECTOR2I(int(round(x * NM)), int(round(y * NM)))


def mm(p):
    return (p.x / NM, p.y / NM)


def near(p, q, d):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= d


def duplicate(item):
    """KiCad 10's bindings differ: ZONE.Duplicate(addToParentGroup) returns a bare BOARD_ITEM, while drawings'
    Duplicate() takes no argument and casts itself."""
    if isinstance(item, pcbnew.ZONE):
        return item.Duplicate(False).Cast()
    return item.Duplicate()


def is_circle(d, layer, r):
    return (d.GetClass() == "PCB_SHAPE" and d.GetShape() == pcbnew.SHAPE_T_CIRCLE and d.GetLayer() == layer
            and abs(d.GetRadius() / NM - r) < 0.05)


def fix_holes(board):
    old = [d for d in board.GetDrawings() if is_circle(d, pcbnew.Edge_Cuts, 4.0)]
    width = old[0].GetWidth() if old else int(0.05 * NM)
    for d in old:
        board.Delete(d)
    for x, y in F.TEMPLATE_HOLES:
        c = pcbnew.PCB_SHAPE(board)
        c.SetShape(pcbnew.SHAPE_T_CIRCLE)
        c.SetLayer(pcbnew.Edge_Cuts)
        c.SetStart(v(x, y))
        c.SetEnd(v(x + 4.0, y))
        c.SetWidth(width)
        board.Add(c)
    labels = [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() == "CONTROL"]
    for t in labels:                                   # each placeholder to the nearest hole's label spot
        tx, ty = mm(t.GetPosition())
        hx, hy = min(F.TEMPLATE_HOLES, key=lambda h: math.hypot(h[0] - tx, h[1] + F.LABEL_DY - ty))
        t.SetPosition(v(hx, hy + F.LABEL_DY))


def fix_trefoils(board):
    src = F.TREFOIL_SRC
    parts = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetLayer() == pcbnew.F_Cu
             and near(mm(z.GetBoundingBox().Centre()), src, 4.0)]
    parts += [d for d in board.GetDrawings() if d.GetClass() == "PCB_SHAPE" and near(mm(d.GetBoundingBox().Centre()), src, 4.0)
              and (d.GetLayer() == pcbnew.F_Mask or is_circle(d, pcbnew.B_Mask, 3.5))]
    if len(parts) != 4 + 3 + 1 + 1:
        sys.exit(f"expected 9 trefoil parts at {src}, found {len(parts)}")
    for lx, ly in F.LED_FACE:
        for p in parts:
            dup = duplicate(p)
            dup.Move(v(lx - src[0], ly - src[1]))
            board.Add(dup)
    for p in parts:
        board.Delete(p)


def swap_guides(board, template):
    for d in list(board.GetDrawings()):
        if d.GetLayer() in GUIDE_LAYERS:
            board.Delete(d)
    axis = v(F.FACE_MIRROR / 2, 0)
    for d in template.GetDrawings():
        if d.GetLayer() not in GUIDE_LAYERS:
            continue
        dup = duplicate(d)
        if d.GetClass() == "PCB_TEXT":
            x, y = mm(d.GetPosition())
            dup.SetPosition(v(F.face_x(x), y))         # readable text, mirrored anchor
        else:
            dup.Mirror(axis, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        board.Add(dup)


def main():
    face_path, template_path = sys.argv[1], sys.argv[2]
    board = pcbnew.LoadBoard(face_path)
    template = pcbnew.LoadBoard(template_path)
    fix_holes(board)
    fix_trefoils(board)
    swap_guides(board, template)
    board.GetTitleBlock().SetTitle(TITLE)              # was "125B Full Board Setup"
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(face_path)
    print("fixed", face_path)


if __name__ == "__main__":
    main()
