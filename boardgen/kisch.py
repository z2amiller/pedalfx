"""Tiny KiCad 10 schematic writer: place library symbols, compute pin positions, draw wires/labels/junctions.

Coordinates are schematic mm, y down. Symbol pins are read from the .kicad_sym files (y up) and transformed
for the instance rotation (0/90/180/270, CCW as KiCad does it). Symbol libraries are searched in order:
the schematic's custom_libs dirs (a project's own <lib>.kicad_sym), kicad-pedal-lib/symbols, then the
stock KiCad symbols. Stdlib only, so it runs under the system python and KiCad's 3.9.
"""
import re
import uuid
from pathlib import Path

KICAD_SYMS = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
PEDAL_SYMS = Path(__file__).resolve().parent.parent.parent / "kicad-pedal-lib" / "symbols"   # ~/Documents/repos/kicad-pedal-lib


def u():
    return str(uuid.uuid4())


GRID = 1.27


def snap(v):
    """KiCad's connection grid is 50 mil; every symbol origin and wire end must sit on it."""
    return round(round(v / GRID) * GRID, 4)


def _balanced(text, start):
    d = 0
    i = start
    while True:
        c = text[i]
        if c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return text[start:i + 1]
        i += 1


def lib_symbol_text(lib, name, custom_libs=None):
    """Return the (symbol "lib:name" ...) block text, with (extends) resolved by copying the parent body."""
    src = None
    if custom_libs is None:
        custom = []
    elif isinstance(custom_libs, (str, Path)):
        custom = [custom_libs]
    else:
        custom = list(custom_libs)
    for base in custom + [PEDAL_SYMS, KICAD_SYMS]:
        p = Path(base) / f"{lib}.kicad_sym"
        if p.exists():
            t = p.read_text()
            m = re.search(r'\n\t\(symbol "%s"\n' % re.escape(name), t)
            if m:
                src = _balanced(t, m.start() + 2)
                break
    if src is None:
        raise KeyError(f"{lib}:{name}")
    ext = re.search(r'\(extends "([^"]+)"\)', src)
    if ext:
        parent = lib_symbol_text(lib, ext.group(1), custom_libs)
        # keep the child's properties, take the parent's drawing units (renamed)
        units = re.findall(r'\n\t\t\(symbol "%s_(\d+_\d+)"' % re.escape(ext.group(1)), parent)
        body = ""
        for unit in units:
            m = re.search(r'\n\t\t\(symbol "%s_%s"\n' % (re.escape(ext.group(1)), unit), parent)
            blk = _balanced(parent, m.start() + 3)
            body += "\n\t\t" + blk.replace(f'(symbol "{ext.group(1)}_{unit}"', f'(symbol "{name}_{unit}"', 1)
        src = src.replace(ext.group(0), "").rstrip()
        assert src.endswith(")")
        src = src[:-1] + body + "\n\t)"
    return src.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def symbol_pins(sym_text):
    """[(number, name, x, y, angle, length)] in symbol coordinates (y up)."""
    pins = []
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)\s*\(length ([\d.]+)\)[\s\S]*?\(name "([^"]*)"[\s\S]*?\(number "([^"]*)"', sym_text):
        x, y, a, l, name, num = m.groups()
        pins.append((num, name, float(x), float(y), int(a), float(l)))
    return pins


class Schematic:
    def __init__(self, project, root_uuid, title, custom_libs=None):
        self.project = project
        self.root_uuid = root_uuid
        self.title = title
        self.custom_libs = custom_libs
        self.libsyms = {}      # "lib:name" -> text
        self.pins = {}         # "lib:name" -> pins
        self.items = []        # emitted s-expr strings
        self.refs = {}         # ref -> (uuid, lib_id, x, y, rot)
        self.pin_pos = {}      # (ref, number) -> (x, y)
        self.wire_ends = []    # list of endpoints for junction detection
        self.segments = []

    # ---- library --------------------------------------------------------------------------
    def use(self, lib_id):
        if lib_id not in self.libsyms:
            lib, name = lib_id.split(":", 1)
            t = lib_symbol_text(lib, name, self.custom_libs)
            self.libsyms[lib_id] = t
            self.pins[lib_id] = symbol_pins(t)
        return self.pins[lib_id]

    # ---- placement ----------------------------------------------------------------------------
    def place(self, lib_id, ref, value, footprint, x, y, rot=0, fields=None, dnp=False, in_bom=True,
              ref_off=(2.54, -1.27), val_off=(2.54, 1.27), hide_value=False, mirror=None):
        pins = self.use(lib_id)
        sid = u()
        x, y = snap(x), snap(y)
        self.refs[ref] = (sid, lib_id, x, y, rot)
        for num, name, px, py, ang, ln in pins:
            # rotate CCW by rot in y-up coords, then to y-down
            import math
            th = math.radians(rot)
            rx = px * math.cos(th) - py * math.sin(th)
            ry = px * math.sin(th) + py * math.cos(th)
            if mirror == "x":
                ry = -ry
            elif mirror == "y":
                rx = -rx
            self.pin_pos[(ref, num)] = (round(x + rx, 4), round(y - ry, 4))
        # KiCad adds the symbol rotation to the property angle; for sideways parts counter-rotate and centre the text
        if rot % 180 == 90:
            pang, pj = 90, None
            if ref_off == (2.54, -1.27) and val_off == (2.54, 1.27):
                ref_off, val_off = (0, -2.54), (0, 2.54)
        else:
            pang, pj = 0, "left"
        props = [
            self._prop("Reference", ref, x + ref_off[0], y + ref_off[1], justify=pj, angle=pang, hide=ref.startswith("#")),
            self._prop("Value", value, x + val_off[0], y + val_off[1], justify=pj, angle=pang, hide=hide_value),
            self._prop("Footprint", footprint, x, y, hide=True),
            self._prop("Datasheet", "", x, y, hide=True),
            self._prop("Description", "", x, y, hide=True),
        ]
        for k, v in (fields or {}).items():
            props.append(self._prop(k, v, x, y, hide=True))
        pin_lines = "".join(f'\n\t\t(pin "{num}"\n\t\t\t(uuid "{u()}")\n\t\t)' for num, *_ in pins)
        mir = f"\n\t\t(mirror {mirror})" if mirror else ""
        self.items.append(
            f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x:g} {y:g} {rot}){mir}\n\t\t(unit 1)\n\t\t(body_style 1)\n'
            f'\t\t(exclude_from_sim no)\n\t\t(in_bom {"yes" if in_bom else "no"})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n'
            f'\t\t(dnp {"yes" if dnp else "no"})\n\t\t(uuid "{sid}")\n' + "\n".join(props) + pin_lines +
            f'\n\t\t(instances\n\t\t\t(project "{self.project}"\n\t\t\t\t(path "/{self.root_uuid}"\n'
            f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
        return sid

    def _prop(self, name, value, x, y, hide=False, justify=None, angle=0):
        h = "\n\t\t\t(hide yes)" if hide else ""
        j = f"\n\t\t\t\t(justify {justify})" if justify else ""
        return (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {x:g} {y:g} {angle}){h}\n\t\t\t(show_name no)\n'
                f'\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t){j}\n\t\t\t)\n\t\t)')

    def pin(self, ref, number):
        return self.pin_pos[(ref, str(number))]

    # ---- wiring -------------------------------------------------------------------------------
    def wire(self, *pts):
        """Polyline through the given points (each (x,y) or (ref, pin))."""
        pts = [self.pin(*p) if isinstance(p[0], str) else (snap(p[0]), snap(p[1])) for p in pts]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            self.segments.append((a, b))
            self.items.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {a[0]:g} {a[1]:g}) (xy {b[0]:g} {b[1]:g})\n\t\t)\n'
                              f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')
        self.wire_ends += [pts[0], pts[-1]]
        return pts

    def manhattan(self, a, b, via="h"):
        """Two-segment wire a->b; via='h' goes horizontal first, 'v' vertical first."""
        a = self.pin(*a) if isinstance(a[0], str) else a
        b = self.pin(*b) if isinstance(b[0], str) else b
        mid = (b[0], a[1]) if via == "h" else (a[0], b[1])
        return self.wire(a, mid, b)

    def label(self, name, ref_pin_or_xy, rot=0, justify="left bottom"):
        x, y = self.pin(*ref_pin_or_xy) if isinstance(ref_pin_or_xy[0], str) else (snap(ref_pin_or_xy[0]), snap(ref_pin_or_xy[1]))
        self.items.append(f'\t(label "{name}"\n\t\t(at {x:g} {y:g} {rot})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
                          f'\t\t\t(justify {justify})\n\t\t)\n\t\t(uuid "{u()}")\n\t)')

    def gnd(self, ref_pin_or_xy, ref="#PWR"):
        """power:GND symbol with its pin exactly on the given point (no wire needed)."""
        x, y = self.pin(*ref_pin_or_xy) if isinstance(ref_pin_or_xy[0], str) else (snap(ref_pin_or_xy[0]), snap(ref_pin_or_xy[1]))
        n = sum(1 for r in self.refs if r.startswith("#PWR")) + 1
        return self.place("power:GND", f"#PWR{n:02d}", "GND", "", x, y, 0, hide_value=False, in_bom=False,
                          ref_off=(0, 0), val_off=(0, 3.81))

    def pwr_flag(self, ref_pin_or_xy):
        """power:PWR_FLAG with its pin on the given point."""
        x, y = self.pin(*ref_pin_or_xy) if isinstance(ref_pin_or_xy[0], str) else (snap(ref_pin_or_xy[0]), snap(ref_pin_or_xy[1]))
        n = sum(1 for r in self.refs if r.startswith("#FLG")) + 1
        return self.place("power:PWR_FLAG", f"#FLG{n:02d}", "PWR_FLAG", "", x, y, 0, in_bom=False,
                          ref_off=(0, 0), val_off=(0, -3.81))

    def junction(self, xy):
        self.items.append(f'\t(junction\n\t\t(at {xy[0]:g} {xy[1]:g})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n\t\t(uuid "{u()}")\n\t)')

    def auto_junctions(self):
        """Add a junction wherever 3+ segment endpoints/pins meet, or a wire end sits on another segment."""
        from collections import Counter
        ends = Counter()
        for a, b in self.segments:
            ends[a] += 1
            ends[b] += 1
        for p in self.pin_pos.values():
            ends[p] += 1
        done = set()
        for p, n in ends.items():
            if n >= 3 and p not in done:
                self.junction(p); done.add(p)
        # T on a segment interior
        for p in list(ends):
            if p in done:
                continue
            for a, b in self.segments:
                if p in (a, b):
                    continue
                if a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1]):
                    self.junction(p); done.add(p); break
                if a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0]):
                    self.junction(p); done.add(p); break

    def text(self, s, x, y, size=1.27):
        s = s.replace('"', '\\"')
        self.items.append(f'\t(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at {x:g} {y:g} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n'
                          f'\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')

    # ---- output ------------------------------------------------------------------------------
    def render(self, paper="A4", rev="0.1", comment=""):
        libs = "\n".join("\t" + t.replace("\n", "\n\t") for t in self.libsyms.values())
        return ("(kicad_sch\n\t(version 20260306)\n\t(generator \"kisch\")\n\t(generator_version \"10.0\")\n"
                f"\t(uuid \"{self.root_uuid}\")\n\t(paper \"{paper}\")\n"
                f"\t(title_block\n\t\t(title \"{self.title}\")\n\t\t(rev \"{rev}\")\n\t\t(company \"z2amiller\")\n\t\t(comment 1 \"{comment}\")\n\t)\n"
                f"\t(lib_symbols\n{libs}\n\t)\n" + "\n".join(self.items) +
                "\n\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")

    def symbol_uuids(self):
        return {ref: v[0] for ref, v in self.refs.items() if not ref.startswith("#")}
