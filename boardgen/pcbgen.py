"""Shared pcbnew helpers for generated boards (run under KiCad's python, see KICAD_PYTHON).

A board generator reads the netlist that kicad-cli exported from the generated schematic, places every
footprint at coordinates it owns, routes BY NET (pads are looked up by net name, never by geometry),
pours the ground, writes silk and saves. This module holds the parts that are the same for every board:
netlist parsing, footprint loading from the stock / kicad-pedal-lib / project libraries (with the library
nickname kept in the FPID), placement with side flipping and orientation fixing, track/via/zone/text
helpers, rounded outlines and a SaveBoard that does not clobber the project file.

Gotchas this code encodes (memory kicad-generated-board-recipe): board.Add(fp) BEFORE Flip or pcbnew
segfaults; LoadBoard needs a blank that keeps (version ...); SaveBoard rewrites <name>.kicad_pro with
defaults; net names with '/' come back from pcbnew as {slash}; FOOTPRINT has no GetFieldByName here.
"""
import math
import re
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
REPOS = HERE.parent.parent                                     # ~/Documents/repos
KICAD_PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
STOCK_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PEDAL_FP = REPOS / "kicad-pedal-lib" / "footprints"
BLANK = HERE / "blank.kicad_pcb"                               # header-only KiCad 10 board (version, layers, setup)

MM = pcbnew.FromMM
F, B = pcbnew.F_Cu, pcbnew.B_Cu


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def mm(v):
    return pcbnew.ToMM(v)


def nn(pad):
    """Pad net name as the netlist spells it (KiCad stores '/' as {slash})."""
    return pad.GetNetname().replace("{slash}", "/")


def stage(n):
    print("STAGE", n, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- netlist -------------------------
def read_netlist(path):
    """kicad-cli kicadsexpr netlist -> (comps, pad_net).

    comps[ref] = {footprint, value, dnp, exclude_from_bom, lcsc}; pad_net[(ref, pin)] = net name. KiCad 10
    writes symbol properties across lines, hence the \\s* in the regexes (a single-line match silently misses)."""
    t = Path(path).read_text()
    comps = {}
    for blk in re.split(r'\n\t\t\(comp\n', t[t.index("(components"):t.index("(libparts")])[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', blk).group(1)
        fp = re.search(r'\(footprint "([^"]*)"\)', blk)
        val = re.search(r'\(value "([^"]*)"\)', blk)
        comps[ref] = {"footprint": fp.group(1) if fp else "", "value": val.group(1) if val else "",
                      "dnp": bool(re.search(r'\(property\s*\(name "dnp"\)', blk)),
                      "exclude_from_bom": bool(re.search(r'\(property\s*\(name "exclude_from_bom"\)', blk)),
                      "lcsc": (re.search(r'\(property\s*\(name "LCSC"\)\s*\(value "([^"]+)"\)', blk) or [None, ""])[1]}
    pad_net = {}
    for blk in re.split(r'\n\t\t\(net\n', t[t.index("(nets"):])[1:]:
        name = re.search(r'\(name "([^"]+)"\)', blk).group(1)
        for r, p in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk):
            pad_net[(r, p)] = name
    return comps, pad_net


# ---------------------------------------------------------------- footprints ----------------------
def fp_lib_dir(lib, project_dir=None, project_lib=None):
    """Directory of a footprint library nickname: the project's own <lib>.pretty, kicad-pedal-lib, or stock."""
    if project_lib and lib == project_lib and project_dir is not None:
        return Path(project_dir) / f"{lib}.pretty"
    if (PEDAL_FP / f"{lib}.pretty").is_dir():
        return PEDAL_FP / f"{lib}.pretty"
    return STOCK_FP / f"{lib}.pretty"


def load_fp(lib_id, project_dir=None, project_lib=None):
    lib, name = lib_id.split(":", 1)
    path = fp_lib_dir(lib, project_dir, project_lib)
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        sys.exit(f"footprint {lib_id} not found in {path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))       # keep the nickname so Update PCB from Schematic sees no change
    return fp


def flip_to_back(fp):
    # KiCad 9/10: Flip(centre, FLIP_DIRECTION); KiCad 8: Flip(centre, bool aFlipLeftRight)
    try:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    except AttributeError:
        fp.Flip(fp.GetPosition(), False)


def header_only(text):
    """Keep only the header blocks of an existing board file (settings, layers, paper, properties)."""
    i = text.index("(kicad_pcb") + len("(kicad_pcb")
    kept, depth, start, j = [text[:i]], 0, None, i
    while j < len(text):
        c = text[j]
        if c == "(":
            if depth == 0:
                start = j
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and start is not None:
                block = text[start:j + 1]
                head = block[1:].split(None, 1)[0]
                if head in ("version", "generator", "generator_version", "general", "paper", "title_block", "layers",
                            "setup", "property", "embedded_fonts"):
                    kept.append("\n\t" + block)
                start = None
            elif depth < 0:
                break
        j += 1
    kept.append("\n)\n")
    return "".join(kept)


def rounded_outline(board, x0, y0, x1, y1, r=1.0, width=0.1, top_notches=(), top_corner_notches=()):
    """Edge.Cuts rectangle with radius-r corners: four lines and four arcs. top_notches = [(xc, width, depth)]
    cuts rectangular notches into the y0 edge (e.g. for a zip tie around the edge). top_corner_notches =
    [(cx, cy, rn)] replaces the top-left and/or top-right rounded corner with a concave circular bite of radius
    rn centred at (cx, cy) (an enclosure's corner screw boss); the side each one belongs to is taken from cx."""
    def line(a, b):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(V(*a)); s.SetEnd(V(*b))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(width)); board.Add(s)

    def arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_ARC); s.SetArcGeometry(V(*start), V(*mid), V(*end))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(width)); board.Add(s)
    k = r * (1 - math.sqrt(0.5))
    # corner bites: (x at the top edge, y at the side edge, arc mid) for the left and right corners
    bites = {}
    for cx, cy, rn in top_corner_notches:
        side = "L" if cx < (x0 + x1) / 2 else "R"
        xs = x1 if side == "R" else x0
        xt = cx - math.sqrt(rn * rn - (cy - y0) ** 2) if side == "R" else cx + math.sqrt(rn * rn - (cy - y0) ** 2)
        ys = cy + math.sqrt(rn * rn - (cx - xs) ** 2)
        dx, dy = cx - xs, cy - y0                                  # from the board corner toward the centre
        n = math.hypot(dx, dy)
        mid = (cx + rn * dx / n, cy + rn * dy / n)
        bites[side] = (xt, ys, mid)
    xa = x0 + r if "L" not in bites else bites["L"][0]
    for xc, w, d in sorted(top_notches):
        line((xa, y0), (xc - w / 2, y0)); line((xc - w / 2, y0), (xc - w / 2, y0 + d))
        line((xc - w / 2, y0 + d), (xc + w / 2, y0 + d)); line((xc + w / 2, y0 + d), (xc + w / 2, y0))
        xa = xc + w / 2
    xb = x1 - r if "R" not in bites else bites["R"][0]
    line((xa, y0), (xb, y0))
    if "R" in bites:
        xt, ys, mid = bites["R"]
        arc((xt, y0), mid, (x1, ys)); line((x1, ys), (x1, y1 - r))
    else:
        arc((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r)); line((x1, y0 + r), (x1, y1 - r))      # top right
    line((x1 - r, y1), (x0 + r, y1))
    arc((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1))          # bottom right
    arc((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r))          # bottom left
    if "L" in bites:
        xt, ys, mid = bites["L"]
        line((x0, y1 - r), (x0, ys)); arc((x0, ys), mid, (xt, y0))
    else:
        line((x0, y1 - r), (x0, y0 + r)); arc((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0))      # top left


# ---------------------------------------------------------------- board ---------------------------
class GenBoard:
    """A board under construction: footprints placed from a netlist, tracks routed by net."""

    def __init__(self, project_dir, name, netlist=None, symbol_uuids=None, template=None, project_lib=None):
        self.project_dir = Path(project_dir)
        self.name = name
        self.project_lib = project_lib if project_lib is not None else name
        self.board = pcbnew.LoadBoard(str(template or BLANK))
        if self.board is None:
            sys.exit(f"blank template failed to load: {template or BLANK}")
        self.nets = {}
        self.fps = {}
        self.comps, self.pad_net = read_netlist(netlist) if netlist else ({}, {})
        self.ids = symbol_uuids or {}

    # ---- nets / footprints ------------------------------------------------------------------
    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(n)
            self.nets[name] = n
        return self.nets[name]

    def place(self, ref, x, y, rot=0, side="F", hide_ref=False, lib_id=None, value=None, pads=None):
        """Place a footprint. lib_id/value default to the netlist component; pads (num -> net) default to the
        netlist. side 'B' flips to the bottom face (rotation is mirrored so the silk reads as intended)."""
        c = self.comps.get(ref, {})
        lib_id = lib_id or c.get("footprint")
        if not lib_id:
            sys.exit(f"{ref}: no footprint")
        fp = load_fp(lib_id, self.project_dir, self.project_lib)
        fp.SetReference(ref)
        fp.SetValue(value if value is not None else c.get("value", ""))
        if ref in self.ids:
            fp.SetPath(pcbnew.KIID_PATH("/" + self.ids[ref]))
        if hide_ref:
            fp.Reference().SetVisible(False)
        self.board.Add(fp)                     # Flip() needs the board for layer mapping: add first
        fp.SetPosition(V(x, y))
        if side == "B":
            flip_to_back(fp)
        fp.SetOrientationDegrees(rot if side == "F" else -rot)
        if c.get("dnp"):
            fp.SetDNP(True)
        if c.get("exclude_from_bom"):
            fp.SetExcludedFromBOM(True)
        if c.get("lcsc"):
            fp.SetField("LCSC", c["lcsc"])
            for f in fp.GetFields():           # no GetFieldByName on FOOTPRINT in this API
                if f.GetName() == "LCSC":
                    f.SetVisible(False)
        for p in fp.Pads():
            n = (pads or {}).get(p.GetNumber()) or self.pad_net.get((ref, p.GetNumber()))
            if n:
                p.SetNet(self.net(n))
        self.fps[ref] = fp
        return fp

    def orient(self, ref, netname, where):
        """Rotate 180 until the pad on `netname` is the leftmost/rightmost/upmost/downmost ('L','R','U','D')."""
        fp = self.fps[ref]
        pads = {}
        for _ in range(2):
            pads = {nn(p): (mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in fp.Pads()}
            others = [xy for n, xy in pads.items() if n != netname]
            me = pads[netname]
            ok = {"L": me[0] < max(o[0] for o in others), "R": me[0] > min(o[0] for o in others),
                  "U": me[1] < max(o[1] for o in others), "D": me[1] > min(o[1] for o in others)}[where]
            if ok:
                return
            fp.SetOrientationDegrees(fp.GetOrientationDegrees() + 180)
        sys.exit(f"{ref}: cannot orient {netname} to {where}: {pads}")

    def pad_xy(self, ref, num):
        for p in self.fps[ref].Pads():
            if p.GetNumber() == str(num):
                return (round(mm(p.GetPosition().x), 3), round(mm(p.GetPosition().y), 3))
        sys.exit(f"no pad {num} on {ref}")

    def pad_by_net(self, ref, netname):
        for p in self.fps[ref].Pads():
            if nn(p) == netname:
                return (round(mm(p.GetPosition().x), 3), round(mm(p.GetPosition().y), 3))
        sys.exit(f"{ref}: no pad on {netname}: {[nn(p) for p in self.fps[ref].Pads()]}")

    def pads_by_net(self, ref, netname):
        return [(round(mm(p.GetPosition().x), 3), round(mm(p.GetPosition().y), 3))
                for p in self.fps[ref].Pads() if nn(p) == netname]

    # ---- copper -----------------------------------------------------------------------------
    def track(self, netname, layer, width, *pts):
        """Polyline of tracks; each point is (x, y) or (ref, pad_number)."""
        pts = [self.pad_xy(*p) if isinstance(p[0], str) else p for p in pts]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(V(*a)); t.SetEnd(V(*b)); t.SetWidth(MM(width)); t.SetLayer(layer); t.SetNet(self.net(netname))
            self.board.Add(t)

    def via(self, netname, x, y, drill=0.3, dia=0.6):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(V(x, y)); v.SetDrill(MM(drill)); v.SetWidth(MM(dia)); v.SetNet(self.net(netname))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        self.board.Add(v)

    def zone(self, layer, pts, netname="GND", clearance=0.3, min_width=0.25, full_connect=True):
        """Ground pour. RF ground defaults to solid pad ties (no thermal spokes) and island removal."""
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer); z.SetNet(self.net(netname))
        z.SetLocalClearance(MM(clearance)); z.SetMinThickness(MM(min_width))
        if full_connect:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(MM(0.3)); z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline(); o.NewOutline()
        for x, y in pts:
            o.Append(MM(x), MM(y))
        self.board.Add(z)
        return z

    def fill_zones(self, passes=4):
        """Fill all zones. Island removal inside ZONE_FILLER races with connectivity in this pcbnew build
        (the same script leaves 0 or 3 islands on different runs), so build connectivity first and refill
        until the outline count stops falling. Returns the per-zone outline counts."""
        def counts():
            return [sum(z.GetFilledPolysList(l).OutlineCount() for l in z.GetLayerSet().Seq()) for z in self.board.Zones()]
        prev = None
        for i in range(passes):
            self.board.BuildConnectivity()
            pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
            cur = counts()
            print("zone fill pass", i + 1, "outlines", cur, file=sys.stderr, flush=True)
            if prev is not None and cur >= prev:
                break
            prev = cur
        return cur

    def outline(self, x0, y0, x1, y1, r=1.0, width=0.1, top_notches=(), top_corner_notches=()):
        rounded_outline(self.board, x0, y0, x1, y1, r, width, top_notches, top_corner_notches)

    # ---- text / title -----------------------------------------------------------------------
    def text(self, txt, x, y, layer, size=0.8, mirror=False, rot=0, justify=None, thickness=None):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(txt); t.SetPosition(V(x, y)); t.SetLayer(layer)
        t.SetTextSize(V(size, size)); t.SetTextThickness(MM(thickness if thickness is not None else size * 0.15))
        if rot:
            t.SetTextAngleDegrees(rot)
        if mirror:
            t.SetMirrored(True)
        if justify == "left":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        elif justify == "left bottom":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT); t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_BOTTOM)
        self.board.Add(t)
        return t

    def title(self, title, rev, comment="", company="z2amiller"):
        tb = self.board.GetTitleBlock()
        tb.SetTitle(title); tb.SetRevision(rev); tb.SetCompany(company)
        if comment:
            tb.SetComment(0, comment)
        self.board.SetTitleBlock(tb)

    # ---- output -----------------------------------------------------------------------------
    def save(self, out=None):
        """SaveBoard, restoring the sibling .kicad_pro that pcbnew rewrites with its defaults.

        The project's text variables (BOARD_STATUS, BOARD_NOTE, ...) are also written as board properties,
        as KiCad itself does on save, so the standalone board file carries them too."""
        out = Path(out) if out else self.project_dir / f"{self.name}.kicad_pcb"
        pro = out.with_suffix(".kicad_pro")
        pro_text = pro.read_text() if pro.exists() else None
        if pro_text:
            import json
            tv = json.loads(pro_text).get("text_variables") or {}
            if tv:
                props = pcbnew.MAP_STRING_STRING()
                for k, v in tv.items():
                    props[k] = v
                self.board.SetProperties(props)
        pcbnew.SaveBoard(str(out), self.board)
        if pro_text is not None:
            pro.write_text(pro_text)
        print(f"saved {out}: {len(self.fps)} footprints, {len(self.nets)} nets")
        return out
