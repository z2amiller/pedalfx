"""Board stage of the Full1590XXTemplate build (run under KiCad's bundled python; see gen_full1590xx.py).

Rewrites a Full125-derived fx-Full1590XX.kicad_pcb in place:
- removes the on-board power filter (D101/R101/L101/C101) and adds BP101, linked to its schematic symbol;
- moves the jacks, DC jack, J101 and its LED D102 to the geometry.py positions; parts that serve one of those move
  with it, and the power cluster takes fx-BlueBlood's layout around the DC jack (clear of the backpack keepout);
- replaces Edge.Cuts with fx-L7's top and sides plus a straight bottom at y 135, copies fx-L7's User.4 enclosure
  (walls, pillars, bosses, R/L markers; not its leftover 125B dimensions), draws the User.2 hardware guides and the
  User.3 Tiny footswitch outlines, and titles the board;
- keeps Full125's GND zone (its settings) reshaped to the new board, and drops the 125B-specific net zones.

usage: python3 board_full1590xx.py PROJECT_DIR BP101_SYMBOL_UUID
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "boardgen"))
import pcbnew  # noqa: E402
import geometry as G  # noqa: E402
from check_full1590xx import _netlist_pins  # noqa: E402
from pcbgen import MM, V, GenBoard, load_fp, mm  # noqa: E402

L7 = Path.home() / "Documents/repos/fx-L7/fx-L7.kicad_pcb"
SETUP_SHEET = "4a6baa1c-d138-4862-b9d0-d98ad688d686"
PROJECT = "fx-Full1590XX"
TITLE = "1590XX Full Board Setup"
L7_MARKERS = ("R", "L")     # L7's player-side markers; its other User.4 texts label 125B dimensions it carried along
U1, U2, U3, U4 = pcbnew.User_1, pcbnew.User_2, pcbnew.User_3, pcbnew.User_4
EDGE = pcbnew.Edge_Cuts

# fx-BlueBlood's power-cluster layout, as offsets from the DC jack J104 (BlueBlood J104 at 110.2, 53.55): (dx, dy, rot)
POWER = {
    "D105": (-0.010489, 4.829022, -90), "C102": (2.275, 28.75, 180), "C103": (0.8, 43.574747, -90),
    "R102": (3.8, 54.45, 90), "R103": (0.8, 54.45, -90), "D104": (7.95, 13.8, -90), "R106": (9.65, 13.55, 90),
    "TP102": (10.3, 36.95, 0), "TP103": (-8.45, 14.7, 0),
}
FOLLOW = {"D106": "J102", "TP101": "J102", "D107": "J103", "TP104": "J103", "TP105": "J101", "TP106": "J101",
          "D103": "D102", "R104": "D102", "R105": "D102"}
N101_BOX = (82.5, 121.5, 98.5, 134.4)        # bottom-left corner, clear of the left header, LED and toggle guides
NAME_TEXT, NAME_AT = "PedalName", (121.0, 134.0)    # left-bottom justified, between the left and centre headers


def xy(item):
    p = item.GetPosition()
    return mm(p.x), mm(p.y)


def shape(layer, kind, width=0.1):
    s = pcbnew.PCB_SHAPE(None, kind)
    s.SetLayer(layer)
    s.SetWidth(MM(width))
    return s


def line(board, layer, a, b, width=0.1):
    s = shape(layer, pcbnew.SHAPE_T_SEGMENT, width)
    s.SetStart(V(*a)); s.SetEnd(V(*b))
    board.Add(s)


def arc(board, layer, a, m, b, width=0.1):
    s = shape(layer, pcbnew.SHAPE_T_ARC, width)
    s.SetArcGeometry(V(*a), V(*m), V(*b))
    board.Add(s)


def circle(board, layer, c, r, width=0.1):
    s = shape(layer, pcbnew.SHAPE_T_CIRCLE, width)
    s.SetCenter(V(*c)); s.SetEnd(V(c[0] + r, c[1]))
    board.Add(s)


def rect(board, layer, a, b, width=0.1):
    s = shape(layer, pcbnew.SHAPE_T_RECTANGLE, width)
    s.SetStart(V(*a)); s.SetEnd(V(*b))
    board.Add(s)


def text(board, layer, txt, x, y, size=1.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt); t.SetPosition(V(x, y)); t.SetLayer(layer)
    t.SetTextSize(V(size, size)); t.SetTextThickness(MM(size * 0.15))
    board.Add(t)


def put(board, ref, x, y, rot=None):
    fp = board.FindFootprintByReference(ref)
    fp.SetPosition(V(x, y))
    if rot is not None:
        fp.SetOrientationDegrees(rot)
    return fp


def outline(board, l7):
    """fx-L7's top edge, top-corner reliefs and sides; sides stop at SIDE_END_Y, then 1 mm corners and a bottom."""
    x0, x1 = G.OUTLINE_BBOX[0], G.OUTLINE_BBOX[1]
    ye, yb = G.SIDE_END_Y, G.BOTTOM_Y
    for d in l7.GetDrawings():
        if d.GetLayer() != EDGE:
            continue
        s = d.Cast()
        pts = [mm(p) for p in (s.GetStart().y, s.GetEnd().y)]
        if s.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            xs = [mm(s.GetStart().x), mm(s.GetEnd().x)]
            if abs(xs[0] - xs[1]) < 1e-6 and min(abs(xs[0] - x0), abs(xs[0] - x1)) < 1e-6 and max(pts) > ye:
                line(board, EDGE, (xs[0], min(pts)), (xs[0], ye), 0.05)       # a side, shortened
                continue
        if max(pts) <= ye and (s.GetShape() != pcbnew.SHAPE_T_ARC or mm(s.GetArcMid().y) <= ye):
            n = s.Duplicate().Cast()
            board.Add(n)
    r = 1.0
    k = r * (1 - math.sqrt(0.5))
    arc(board, EDGE, (x0, ye), (x0 + k, yb - k), (x0 + r, yb), 0.05)
    arc(board, EDGE, (x1 - r, yb), (x1 - k, yb - k), (x1, ye), 0.05)
    line(board, EDGE, (x0 + r, yb), (x1 - r, yb), 0.05)


def guides(board):
    for label, x, y, d in G.GUIDES:
        circle(board, U2, (x, y), d / 2)
        text(board, U2, label, x, y - d / 2 - 1.2, 0.8)
    x0, y0, x1, y1 = G.DC_GUIDE
    rect(board, U2, (x0, y0), (x1, y1))
    text(board, U2, "DC JACK side C Y-5..+5", (x0 + x1) / 2, y0 - 1.2, 0.8)
    cx, cy = G.CENTRE
    line(board, U2, (G.OUTLINE_BBOX[0] - 5, cy), (G.OUTLINE_BBOX[1] + 5, cy))
    line(board, U2, (cx, G.OUTLINE_BBOX[2] - 5), (cx, G.SWITCH_Y + 12))
    text(board, U2, "Enclosure centre (0, 0 Tayda)", cx + 1, cy - 1, 0.8)
    text(board, U2, "2-switch builds use Y -38/+38 only (L7's Tayda template); 3-switch builds add the centre",
         G.OUTLINE_BBOX[0], G.SWITCH_Y + 9, 1.0)
    for sx in G.SWITCH_X:
        a = (sx + G.TINY_BOX[0], G.SWITCH_Y + G.TINY_BOX[1])
        b = (sx + G.TINY_BOX[2], G.SWITCH_Y + G.TINY_BOX[3])
        rect(board, U3, a, b)
        px, py = G.header_pin1(sx)
        for k in range(G.PINS):
            circle(board, U3, (px + G.PITCH * k, py), 0.4)
    text(board, U3, "Tiny footswitch boards and header pin centres", G.OUTLINE_BBOX[0], G.SWITCH_Y + 11.5, 1.0)


def main():
    proj, bp_uuid = Path(sys.argv[1]), sys.argv[2]
    pcb = proj / f"{PROJECT}.kicad_pcb"
    fp = load_fp("Backpack_Pedal:Backpack_Power_v1")    # before any board edit: FootprintLoad fails after them
    gb = GenBoard(proj, PROJECT, template=pcb)
    board = gb.board
    l7 = pcbnew.LoadBoard(str(L7))
    orig = {fp.GetReference(): xy(fp) for fp in board.GetFootprints()}
    orig_pads = [(f.GetReference(), *xy(p)) for f in board.GetFootprints() for p in f.Pads()
                 if f.GetReference() not in G.REMOVED]

    for ref in G.REMOVED:
        board.Delete(board.FindFootprintByReference(ref))

    fp.SetReference("BP101"); fp.SetValue("Backpack_Power_v1")
    for f in fp.GetFields():
        if f.GetName() == "Description":
            f.SetText("")                             # as its schematic symbol (and fx-BlueBlood's BP101)
    fp.SetPath(pcbnew.KIID_PATH(f"/{SETUP_SHEET}/{bp_uuid}"))
    board.Add(fp)
    pins = _netlist_pins(proj)                    # pad nets as the schematic gives them, unconnected-(...) ones too
    for p in fp.Pads():
        name = pins.get(("BP101", p.GetNumber()))
        if name is None:
            continue
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        p.SetNet(net)

    for ref in ("J102", "J103", "J104", "J101", "BP101"):
        x, y, rot, _layer = G.FOOTPRINTS[ref]
        put(board, ref, x, y, rot)
    cx, cy, _rot, _layer = G.FOOTPRINTS["D102"]
    put(board, "D102", cx + G.LED_PAD1_DX, cy)             # B.Cu at rot 180: pad 1 sits 1.27 mm east of the body
    new = {r: xy(board.FindFootprintByReference(r)) for r in ("J101", "J102", "J103", "J104", "D102")}
    for ref, anchor in FOLLOW.items():
        dx, dy = new[anchor][0] - orig[anchor][0], new[anchor][1] - orig[anchor][1]
        put(board, ref, orig[ref][0] + dx, orig[ref][1] + dy)
    jx, jy = new["J104"]
    for ref, (dx, dy, rot) in POWER.items():
        put(board, ref, jx + dx, jy + dy, rot)
    n101 = board.FindFootprintByReference("N101")
    bb = n101.GetBoundingBox(False)
    w, h = mm(bb.GetWidth()), mm(bb.GetHeight())
    ox, oy = xy(n101)
    bx, by = mm(bb.GetX()), mm(bb.GetY())
    put(board, "N101", N101_BOX[0] + (ox - bx), N101_BOX[3] - h + (oy - by))
    if w > N101_BOX[2] - N101_BOX[0] or h > N101_BOX[3] - N101_BOX[1]:
        sys.exit(f"N101 ({w:.1f} x {h:.1f} mm) does not fit {N101_BOX}")

    # a silk text labels the part with the nearest pad (within 15 mm) and moves with it; the board's name label goes
    # to NAME_AT. The 125B jack-spacing dimensions on F.SilkS no longer measure anything: dropped.
    moved = {f.GetReference(): xy(f) for f in board.GetFootprints()}
    for d in list(board.GetDrawings()):
        if d.GetLayer() != pcbnew.F_SilkS:
            continue
        if d.GetClass().startswith("PCB_DIM"):
            board.Delete(d)
        elif d.GetClass() == "PCB_TEXT" and d.GetText().startswith(NAME_TEXT):
            d.SetPosition(V(*NAME_AT))
        elif d.GetClass() == "PCB_TEXT":
            x, y = xy(d)
            ref, px, py = min(orig_pads, key=lambda q: math.dist((x, y), q[1:]))
            if math.dist((x, y), (px, py)) > 15:
                sys.exit(f"silk text {d.GetText()!r} is over 15 mm from every pad: give it a place in this script")
            d.SetPosition(V(x + moved[ref][0] - orig[ref][0], y + moved[ref][1] - orig[ref][1]))

    # fields the 125B's deeper board had room for (the header test points' vertical refs) would cross the new bottom
    # edge: lay them horizontal, centred just above their part's pads
    for f in board.GetFootprints():
        for fld in f.GetFields():
            if (fld.IsVisible() and fld.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
                    and mm(fld.GetBoundingBox().GetBottom()) > G.BOTTOM_Y - 1.0):
                top = min(mm(p.GetBoundingBox().GetY()) for p in f.Pads())
                fld.SetTextAngleDegrees(0)
                fld.SetPosition(V(xy(f)[0], top - 0.3 - mm(fld.GetBoundingBox().GetHeight()) / 2))

    for d in list(board.GetDrawings()):
        if d.GetLayer() in (EDGE, U2, U3, U4):
            board.Delete(d)
    for t in list(board.GetTracks()):          # Full125's routing is for the 125B positions; the template ships unrouted
        board.Delete(t)
    # L7's walls, lid-screw pillars and boss rectangles, and its R/L markers. Its eight dimensions are 125B
    # screw/edge spacings (six at Full125's coordinates, two moved aside unchanged) and go, with their labels.
    for d in l7.GetDrawings():
        if d.GetLayer() != U4 or d.GetClass().startswith("PCB_DIM"):
            continue
        if d.GetClass() == "PCB_TEXT" and d.GetText() not in L7_MARKERS:
            continue
        board.Add(d.Duplicate().Cast())
    outline(board, l7)
    guides(board)

    x0, x1, y0, y1 = G.OUTLINE_BBOX
    for z in list(board.Zones()):
        if z.GetIsRuleArea() and z.GetParentFootprint():
            continue
        if z.GetNetname() != "GND":
            board.Delete(z)
            continue
        o = z.Outline()
        o.RemoveAllContours()
        o.NewOutline()
        for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            o.Append(MM(px), MM(py))
    board.GetTitleBlock().SetTitle(TITLE)
    gb.fill_zones()                               # else the saved pour is Full125's 125B fill
    gb.save()


if __name__ == "__main__":
    main()
