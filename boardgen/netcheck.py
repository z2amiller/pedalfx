"""Export a schematic's netlist with kicad-cli and check it against the intended connectivity.

A board generator keeps an EXPECTED table: {net_label: {"REF.pin", ...}}. Every group must be exactly one
exported net with no extra members; nets the table does not mention are reported as warnings. Net
labels are informational (matching is by membership), so the schematic's auto-generated names are fine.
"""
import re
import subprocess
import sys
from pathlib import Path

KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def export_netlist(sch_path, net_path):
    subprocess.run([KCLI, "sch", "export", "netlist", "--format", "kicadsexpr", "--output", str(net_path), str(sch_path)],
                   check=True, capture_output=True)
    return Path(net_path)


def parse_nets(text):
    """{net name: {"REF.pin", ...}} from a kicadsexpr netlist."""
    nets_sec = text[text.index("(nets"):]
    nets = {}
    for blk in re.split(r'\n\t\t\(net\n', nets_sec)[1:]:
        name = re.search(r'\(name "([^"]+)"\)', blk).group(1)
        nets[name] = set(f"{r}.{p}" for r, p in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk))
    return nets


def check(nets, expected, quiet=False):
    ok = True
    used = set()
    for ename, members in expected.items():
        hits = [n for n, nodes in nets.items() if members <= nodes]
        if len(hits) != 1:
            print(f"FAIL {ename}: expected one net containing {sorted(members)}, found {hits}")
            ok = False
            continue
        n = hits[0]
        extra = nets[n] - members
        if extra:
            print(f"FAIL {ename} (as {n}): unexpected extra nodes {sorted(extra)}")
            ok = False
        used.add(n)
        if not quiet:
            print(f"ok   {ename:11s} -> {n:22s} {len(members)} nodes")
    for n, nodes in nets.items():
        if n not in used and nodes:
            print(f"WARN unexpected net {n}: {sorted(nodes)}")
    print("NETLIST", "OK" if ok else "MISMATCH")
    return ok


def main(sch_path, net_path, expected):
    export_netlist(sch_path, net_path)
    ok = check(parse_nets(Path(net_path).read_text()), expected)
    sys.exit(0 if ok else 1)
