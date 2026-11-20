#!/usr/bin/env python3
"""Build Full1590XXTemplate's source project (fx-Full1590XX) in a scratch dir.

Stages:
  sheets  clone Full125Template, upgrade the sheets to KiCad 10, swap the on-board power filter for the BP101
          power-backpack connector (fx-BlueBlood's edit) and title the root sheet.
  board   rewrite the board with fx-L7's 1590XX mechanics (board_full1590xx.py, under KiCad's python).
  all     both, then check_full1590xx.py.

Spec: ~/Claude/docs/superpowers/specs/2026-11-19-1590xx-template-design.md.  Install the result with
`pedal-fleet new-template` (see the plan).

usage: gen_full1590xx.py --scratch DIR [--stage sheets|board|all]
"""
import argparse
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent
sys.path.insert(0, str(TEMPLATES.parent / "boardgen"))
import kisch  # noqa: E402

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
FULL125 = TEMPLATES / "Full125Template"
FLEET = TEMPLATES / "_fleet"
PROJECT = "fx-Full1590XX"
ROOT_UUID = "51dd7ff8-5817-4680-be8c-9c82067deaa5"                  # Full125's root sheet
SETUP_SHEET = "4a6baa1c-d138-4862-b9d0-d98ad688d686"                # Full125's Board Basic Setup sheet symbol
SETUP_PATH = ROOT_UUID + "/" + SETUP_SHEET
TITLE = "1590XX Full Board Setup"
U = kisch.u


# ---- symbol library helpers and Sch (copied from fx-BlueBlood tools/gen_blueblood.py) --------------------------
def _children(block):
    out, i = [], block.index("(", 1)
    while i < len(block) - 1:
        if block[i] == "(":
            c = kisch._balanced(block, i)
            out.append(c)
            i += len(c)
        else:
            i += 1
    return out


def _lib_block(lib, name):
    for base in [kisch.PEDAL_SYMS, kisch.KICAD_SYMS]:
        f = Path(base) / f"{lib}.kicad_sym"
        if f.exists():
            t = f.read_text()
            m = re.search(r'\n\t\(symbol "%s"\n' % re.escape(name), t)
            if m:
                return kisch._balanced(t, m.start() + 2)
    raise KeyError(name)


def flatten(lib_id):
    """Flatten a derived library symbol the way KiCad caches it."""
    lib, name = lib_id.split(":", 1)
    child = _lib_block(lib, name)
    ext = re.search(r'\(extends "([^"]+)"\)', child)
    if not ext:
        return None
    parent = _lib_block(lib, ext.group(1))
    key = lambda c: re.match(r'\((\S+)(?: "([^"]*)")?', c).groups()
    pc, cc = _children(parent), [c for c in _children(child) if not c.startswith("(extends")]
    head = [c for c in pc if not c.startswith(("(property", "(symbol", "(embedded_fonts"))]
    chead = {key(c)[0]: c for c in cc if not c.startswith(("(property", "(symbol", "(embedded_fonts"))}
    head = [chead.pop(key(c)[0], c) for c in head] + list(chead.values())
    cprops = [c for c in cc if c.startswith("(property")]
    names = {key(c)[1] for c in cprops}
    props = cprops + [c for c in pc if c.startswith("(property") and key(c)[1] not in names]
    units = [c.replace(f'(symbol "{ext.group(1)}_', f'(symbol "{name}_', 1) for c in pc if c.startswith("(symbol")]
    body = head + props + units + ["(embedded_fonts no)"]
    return f'(symbol "{lib_id}"\n\t\t' + "\n\t\t".join(body) + "\n\t)"


class Sch(kisch.Schematic):
    """kisch with per-unit placement, free field placement/justification and own #PWR numbering."""

    def __init__(self, *a, pwr=201, flg=201, **k):
        super().__init__(*a, **k)
        self.npwr, self.nflg = pwr, flg

    def use(self, lib_id):
        if lib_id not in self.libsyms:
            super().use(lib_id)
            flat = flatten(lib_id)
            if flat:
                self.libsyms[lib_id] = flat
                self.pins[lib_id] = kisch.symbol_pins(flat)
        return self.pins[lib_id]

    def part(self, lib_id, ref, value, fp, x, y, rot=0, mirror=None, unit=1, fields=None,
             ref_at=None, val_at=None, just="left", pang=None, hide_value=False, in_bom=True, hide_ref=False):
        self.use(lib_id)
        text = self.libsyms[lib_id]
        name = lib_id.split(":", 1)[1]
        pins = []
        for um in re.finditer(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(name), text):
            if int(um.group(1)) in (0, unit):
                pins += kisch.symbol_pins(kisch._balanced(text, um.start()))
        sid = U()
        x, y = kisch.snap(x), kisch.snap(y)
        th = math.radians(rot)
        for num, _n, px, py, _a, _l in pins:
            rx = px * math.cos(th) - py * math.sin(th)
            ry = px * math.sin(th) + py * math.cos(th)
            if mirror == "x":
                ry = -ry
            elif mirror == "y":
                rx = -rx
            self.pin_pos[(ref, num)] = (round(x + rx, 4), round(y - ry, 4))
        self.refs[f"{ref}:{unit}"] = (sid, lib_id, x, y, rot)
        if pang is None:
            pang = 90 if rot % 180 == 90 else 0
        ref_at = ref_at or (x + 2.54, y - 1.27)
        val_at = val_at or (x + 2.54, y + 1.27)
        j = None if just == "center" else just
        props = [
            self._prop("Reference", ref, *ref_at, justify=j, angle=pang, hide=hide_ref or ref.startswith("#")),
            self._prop("Value", value, *val_at, justify=j, angle=pang, hide=hide_value),
            self._prop("Footprint", fp, x, y, hide=True),
            self._prop("Datasheet", "", x, y, hide=True),
            self._prop("Description", "", x, y, hide=True),
        ]
        for k, v in (fields or {}).items():
            props.append(self._prop(k, v, x, y, hide=True))
        pin_lines = "".join(f'\n\t\t(pin "{num}"\n\t\t\t(uuid "{U()}")\n\t\t)' for num, *_ in pins)
        mir = f"\n\t\t(mirror {mirror})" if mirror else ""
        self.items.append(
            f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x:g} {y:g} {rot}){mir}\n\t\t(unit {unit})\n\t\t(body_style 1)\n'
            f'\t\t(exclude_from_sim no)\n\t\t(in_bom {"yes" if in_bom else "no"})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n'
            f'\t\t(dnp no)\n\t\t(uuid "{sid}")\n' + "\n".join(props) + pin_lines +
            f'\n\t\t(instances\n\t\t\t(project "{self.project}"\n\t\t\t\t(path "/{self.root_uuid}"\n'
            f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit {unit})\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
        return sid

    def _xy(self, p):
        return self.pin(*p) if isinstance(p[0], str) else (kisch.snap(p[0]), kisch.snap(p[1]))

    def power(self, lib_id, value, p, rot=0):
        x, y = self._xy(p)
        ref = f"#PWR0{self.npwr}"
        self.npwr += 1
        return self.part(lib_id, ref, value, "", x, y, rot, in_bom=False, ref_at=(x, y),
                         val_at=(x, y + 3.81) if rot == 180 else (x, y - 3.81), just="center")

    def pwr_flag(self, p):
        x, y = self._xy(p)
        ref = f"#FLG0{self.nflg}"
        self.nflg += 1
        return self.part("power:PWR_FLAG", ref, "PWR_FLAG", "", x, y, 0, in_bom=False, ref_at=(x, y),
                         val_at=(x, y - 3.81), just="center")

    def w(self, *pts):
        return self.wire(*[self._xy(p) for p in pts])


def toplevel(text):
    """[(start, end)] spans of depth-1 items."""
    spans, i = [], text.index("\n\t(")
    body_end = text.rstrip().rfind(")")
    while True:
        j = text.find("\n\t(", i)
        if j == -1 or j >= body_end:
            break
        blk = kisch._balanced(text, j + 2)
        spans.append((j + 2, j + 2 + len(blk)))
        i = j + 2 + len(blk)
    return spans


def splice(base, s, title_block=None):
    lib_start = base.index("\t(lib_symbols\n") + 1
    lib_blk = kisch._balanced(base, lib_start)
    have = set(re.findall(r'\n\t\t\(symbol "([^"]+)"', lib_blk))
    add = [t for lid, t in s.libsyms.items() if lid not in have] if s else []
    new_lib = lib_blk[:-1].rstrip() + "".join("\n\t\t" + t.replace("\n", "\n\t") for t in add) + "\n\t)"
    out = base[:lib_start] + new_lib + base[lib_start + len(lib_blk):]
    k = out.find("\t(sheet_instances")
    if k == -1:
        k = out.rstrip().rfind(")")
    out = out[:k] + "\n".join(s.items if s else []) + "\n" + out[k:]
    if title_block:
        p = out.index("\t(lib_symbols")
        out = out[:p] + title_block + out[p:]
    return out


def drop_unused_libs(out):
    lib_start = out.index("\t(lib_symbols\n") + 1
    lib_blk = kisch._balanced(out, lib_start)
    used = set(re.findall(r'\(lib_id "([^"]+)"\)', out))
    for name in re.findall(r'\n\t\t\(symbol "([^"]+)"', lib_blk):
        if name not in used:
            m = re.search(r'\n\t\t\(symbol "%s"\n' % re.escape(name), lib_blk)
            blk = kisch._balanced(lib_blk, m.start() + 3)
            lib_blk = lib_blk.replace("\n\t\t" + blk, "", 1)
    return out[:lib_start] + lib_blk + out[lib_start + len(kisch._balanced(out, lib_start)):]


def edit_setup(base):
    """Board Basic Setup: BP101 replaces D101/R101/L101/C101 (fx-BlueBlood's edit).  Returns (text, bp101_uuid)."""
    gone_refs = {"D101", "R101", "L101", "C101"}
    gone_wires = {(36.83, 102.87, 39.37, 102.87), (44.45, 102.87, 46.99, 102.87), (52.07, 102.87, 54.61, 102.87),
                  (59.69, 102.87, 62.23, 102.87), (62.23, 102.87, 71.12, 102.87), (71.12, 102.87, 83.82, 102.87),
                  (62.23, 102.87, 62.23, 110.49), (62.23, 115.57, 62.23, 123.19),
                  (71.12, 102.87, 71.12, 110.49), (71.12, 115.57, 71.12, 123.19)}
    gone_junctions = {(62.23, 102.87), (71.12, 102.87), (62.23, 123.19), (71.12, 123.19)}
    keep, removed = [], []
    spans = toplevel(base)
    head, tail = base[:spans[0][0]], base[spans[-1][1]:]
    for a, b in spans:
        blk = base[a:b]
        if blk.startswith("(symbol"):
            r = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
            if r in gone_refs:
                removed.append(r)
                continue
            if r == "C102":   # slide C102 right by 5.08 mm to clear the backpack pins
                blk = re.sub(r'\(at ([-\d.]+) ([-\d.]+)( \d+)?\)',
                             lambda m: f'(at {float(m.group(1)) + 5.08:g} {m.group(2)}{m.group(3) or ""})', blk)
        elif blk.startswith("(wire"):
            p = tuple(map(float, re.search(r'\(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)', blk).groups()))
            if p in gone_wires or (p[2], p[3], p[0], p[1]) in gone_wires:
                removed.append(f"wire{p}")
                continue
        elif blk.startswith("(junction"):
            p = tuple(map(float, re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', blk).groups()))
            if p in gone_junctions:
                removed.append(f"junction{p}")
                continue
        elif blk.startswith("(text_box \"Power Section"):
            old = "Power Section - Reverse polarity\\nprotection, filtering, and a 1/2 VCC\\nVREF."
            assert old in blk
            blk = blk.replace(old, "Power Section - power backpack BP101\\n(+9V_RAW out, filtered +9VA back)\\nand a 1/2 VCC VREF.")
        keep.append(blk)
    assert sorted(r for r in removed if not r.startswith(("wire", "junction"))) == sorted(gone_refs), removed
    assert sum(r.startswith("wire") for r in removed) == len(gone_wires), removed
    assert sum(r.startswith("junction") for r in removed) == len(gone_junctions), removed
    body = head + "\n\t".join(keep) + tail

    s = Sch(PROJECT, SETUP_PATH, "", pwr=140, flg=140)
    bp = s.part("Connector_Backpack_Pedal:Backpack_Power_v1", "BP101", "Backpack_Power_v1",
                "Backpack_Pedal:Backpack_Power_v1", 53.34, 111.76, 0, ref_at=(53.34, 103.0), val_at=(53.34, 120.0),
                just="center", hide_value=True)
    # P1 +9V_RAW (68.58,106.68)  P4 +9VA (68.58,109.22)  A4 (68.58,114.3)  A1 (68.58,116.84); GND pins y=121.92
    s.w(("BP101", "P1"), (71.12, 106.68), (71.12, 104.14))
    s.power("power:+9V", "+9V", (71.12, 104.14))
    s.w(("BP101", "P4"), (73.66, 109.22), (73.66, 102.87), (83.82, 102.87))
    s.w((36.83, 102.87), (39.37, 102.87))
    s.pwr_flag((39.37, 102.87))
    s.no_connect(s.pin("BP101", "A4"))
    s.no_connect(s.pin("BP101", "A1"))
    for p in ("P2", "P3", "A2", "A3"):
        x, y = s.pin("BP101", p)
        s.w((x, y), (x, 123.19))
        s.junction((x, 123.19))
    s.w((76.2, 102.87), (76.2, 110.49))
    s.w((76.2, 115.57), (76.2, 123.19))
    s.junction((76.2, 102.87))
    s.junction((76.2, 123.19))
    return drop_unused_libs(splice(body, s)), bp


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{' '.join(map(str, cmd))} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def build_sheets(scratch: Path) -> str:
    """Clone Full125Template into scratch/fx-Full1590XX, upgrade and edit its sheets; return BP101's symbol uuid."""
    scratch = Path(scratch)
    proj = scratch / PROJECT
    if proj.exists():
        shutil.rmtree(proj)
    scratch.mkdir(parents=True, exist_ok=True)
    _run(["uv", "run", "pedal-fleet", "clone", PROJECT, "--from", str(FULL125), "--dest", str(proj),
          "--no-git", "--no-process-check"], cwd=FLEET)
    root, setup = proj / f"{PROJECT}.kicad_sch", proj / "board_setup.kicad_sch"
    for sheet in (root, setup):
        _run([KICAD_CLI, "sch", "upgrade", str(sheet)])
    text, bp = edit_setup(setup.read_text())
    setup.write_text(text)
    rt = root.read_text()
    assert "(title_block" not in rt, "Full125's root sheet unexpectedly has a title block"
    p = rt.index("\t(lib_symbols")
    rt = rt[:p] + f'\t(title_block\n\t\t(title "{TITLE}")\n\t\t(company "z2amiller")\n\t)\n' + rt[p:]
    root.write_text(rt)
    return bp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--stage", choices=["sheets", "board", "all"], default="all")
    a = ap.parse_args()
    if a.stage in ("sheets", "all"):
        print("BP101 uuid", build_sheets(a.scratch))


if __name__ == "__main__":
    main()
