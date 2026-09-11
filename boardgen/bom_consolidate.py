#!/usr/bin/env python3
"""Consolidated LCSC shopping list across generated boards (bead kicad-wbhj).

Each input is (variant name, netlist path or project dir, quantity, overrides {ref: (value, lcsc)}). Parts with the
dnp or exclude_from_bom property are skipped, overrides replace a part's value/LCSC (the 772 fit of the UHF module),
and rows are grouped by LCSC number with one column per variant. Spares: +20 % rounded up, at least +2 for 0603
passives and +1 for everything else. Catalog description/price come from the local JLC FTS5 copy when present.

Netlists for project directories are exported with kicad-cli into --work-dir (default: a fresh tempdir), never into
the source repo itself, since another session may have that repo's working tree in use concurrently; a `.net` path
is used as-is.

Usage: bom_consolidate.py --out list.csv --board mod-1090=/path/util-UHFModule:2 --board mod-772=/path/util-UHFModule:2:C11=0R/C21189,C12=0R/C21189,L11=DNP,FL1=TA2429A/C46551386,FL2=TA2429A/C46551386 --board vhf=/path/util-AntennaVHFCenter:2
"""
import argparse
import csv
import math
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path

KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
CATALOG = Path.home() / "Claude" / "kicad-jlcpcb-tools" / "jlcpcb" / "current-parts-fts5.db"
SMALL = re.compile(r"_0603_|_0402_|_0805_")


def parts_from_netlist(net_path):
    """{ref: (value, lcsc, footprint name)} for every fitted, BOM-included part with an LCSC number."""
    t = Path(net_path).read_text()
    out = {}
    body = t[t.index("(components"):t.index("(libparts")]
    # kicad-cli's real netlist output puts "(comp" alone on a line ("\n\t\t(comp\n\t\t\t(ref ...)");
    # a hand-written fixture may put "(ref ...)" straight after it on the same line ("(comp (ref ...)").
    # Split on either by consuming exactly the one whitespace character that follows "(comp".
    for blk in re.split(r'\n\t\t\(comp\s', body)[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', blk).group(1)
        if re.search(r'\(property\s*\(name "dnp"\)', blk) or re.search(r'\(property\s*\(name "exclude_from_bom"\)', blk):
            continue
        val = (re.search(r'\(value "([^"]*)"\)', blk) or [None, ""])[1]
        fp = (re.search(r'\(footprint "([^"]*)"\)', blk) or [None, ""])[1].split(":")[-1]
        lcsc = (re.search(r'\(property\s*\(name "LCSC"\)\s*\(value "([^"]+)"\)', blk) or [None, ""])[1]
        if lcsc:
            out[ref] = (val, lcsc, fp)
    return out


def netlist_for(source, work_dir):
    """A .net path is used as is; a project dir gets its schematic exported into work_dir as <project name>.net.

    Never writes into the source repo: another session may be committing there while this runs.
    """
    p = Path(source)
    if p.suffix == ".net":
        return p
    sch = p / f"{p.name}.kicad_sch"
    net = Path(work_dir) / f"{p.name}.net"
    subprocess.run(
        [KCLI, "sch", "export", "netlist", "--format", "kicadsexpr", "--output", str(net), str(sch)],
        check=True, capture_output=True,
    )
    return net


def spares(total, footprint):
    return max(math.ceil(total * 0.2), 2 if SMALL.search("_" + footprint + "_") else 1)


def consolidate(boards):
    """boards: [(variant, netlist path, qty, overrides)] -> rows sorted by LCSC, each {lcsc, value, footprint, <variant>: n, total}."""
    rows = {}
    variants = [b[0] for b in boards]
    for variant, net, qty, overrides in boards:
        parts = parts_from_netlist(net)
        for ref, (val, lcsc) in overrides.items():
            if ref in parts or lcsc:
                parts[ref] = (val, lcsc, parts.get(ref, ("", "", ""))[2]) if lcsc else None
        for ref, spec in parts.items():
            if spec is None:
                continue
            val, lcsc, fp = spec
            r = rows.setdefault(lcsc, {"lcsc": lcsc, "value": val, "footprint": fp, **{v: 0 for v in variants}, "total": 0})
            r[variant] += 1
            r["total"] += qty
    return sorted(rows.values(), key=lambda r: r["lcsc"])


def catalog(lcsc):
    if not CATALOG.exists():
        return ("", "", "")
    con = sqlite3.connect(CATALOG)
    row = con.execute('select "MFR.Part", Description, Price from parts where "LCSC Part"=?', (lcsc,)).fetchone()
    con.close()
    return row or ("", "", "")


def parse_board(arg, work_dir=None):
    name, rest = arg.split("=", 1)
    bits = rest.split(":")
    source, qty = bits[0], int(bits[1])
    overrides = {}
    if len(bits) > 2:
        for item in bits[2].split(","):
            ref, spec = item.split("=")
            if spec == "DNP":
                overrides[ref] = ("", "")
            else:
                val, lcsc = spec.split("/")
                overrides[ref] = (val, lcsc)
    return name, netlist_for(source, work_dir), qty, overrides


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", required=True, help="name=<dir or .net>:<qty>[:REF=val/LCSC,REF=DNP,...]")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work-dir", default=None,
                     help="directory for kicad-cli netlist exports (default: a fresh tempdir; never the source repo)")
    a = ap.parse_args()
    work_dir = a.work_dir or tempfile.mkdtemp(prefix="bom_")
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    boards = [parse_board(b, work_dir) for b in a.board]
    variants = [b[0] for b in boards]
    rows = consolidate(boards)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["LCSC", "MFR part", "value", "footprint", "description", "price tiers",
                    *[f"per {v}" for v in variants], "total", "spares", "order qty"])
        for r in rows:
            mfr, desc, price = catalog(r["lcsc"])
            sp = spares(r["total"], r["footprint"])
            w.writerow([r["lcsc"], mfr, r["value"], r["footprint"], desc, price,
                        *[r[v] for v in variants], r["total"], sp, r["total"] + sp])
    print(f"{len(rows)} LCSC lines -> {a.out} (netlists exported into {work_dir})")


if __name__ == "__main__":
    main()
