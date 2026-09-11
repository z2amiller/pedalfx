import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bom_consolidate
from bom_consolidate import parts_from_netlist, consolidate, spares, parse_board

NET = '''(export (version "E")
	(components
		(comp (ref "C1")
			(value "100p")
			(footprint "Capacitor_SMD:C_0603_1608Metric")
			(property (name "LCSC") (value "C14858")))
		(comp (ref "C2")
			(value "100p")
			(footprint "Capacitor_SMD:C_0603_1608Metric")
			(property
				(name "LCSC")
				(value "C14858")))
		(comp (ref "R9")
			(value "0R (DNP)")
			(footprint "Resistor_SMD:R_0603_1608Metric")
			(property (name "LCSC") (value "C21189"))
			(property (name "dnp")))
		(comp (ref "J1")
			(value "pigtail")
			(footprint "RF_Antenna:Coax_RG316_Solder")
			(property (name "exclude_from_bom"))))
	(libparts)
	(nets))
'''

def test_parts_skip_dnp_and_excluded(tmp_path):
    p = tmp_path / "a.net"; p.write_text(NET)
    parts = parts_from_netlist(p)
    assert parts == {"C1": ("100p", "C14858", "C_0603_1608Metric"), "C2": ("100p", "C14858", "C_0603_1608Metric")}

def test_overrides_and_totals(tmp_path):
    p = tmp_path / "a.net"; p.write_text(NET)
    rows = consolidate([("mod-1090", p, 2, {}), ("mod-772", p, 2, {"C1": ("0R", "C21189")})])
    by = {r["lcsc"]: r for r in rows}
    assert by["C14858"]["mod-1090"] == 2 and by["C14858"]["mod-772"] == 1 and by["C14858"]["total"] == 6
    assert by["C21189"]["mod-772"] == 1 and by["C21189"]["total"] == 2

def test_spares_rule():
    assert spares(6, "C_0603_1608Metric") == 2 and spares(20, "C_0603_1608Metric") == 4
    assert spares(4, "DFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.6mm") == 1 and spares(10, "SMD3838") == 2

def test_parse_board_overrides_and_no_overrides(monkeypatch):
    # netlist_for is monkeypatched to return the source path unchanged, so no kicad-cli call happens here.
    monkeypatch.setattr(bom_consolidate, "netlist_for", lambda source, work_dir: Path(source))

    name, net, qty, overrides = parse_board("vhf=/some/dir:2", work_dir="/unused")
    assert name == "vhf"
    assert net == Path("/some/dir")
    assert qty == 2
    assert overrides == {}

    name, net, qty, overrides = parse_board(
        "mod-772=/some/other/dir:2:C11=0R/C21189,L11=DNP,FL1=TA2429A/C46551386", work_dir="/unused"
    )
    assert name == "mod-772"
    assert net == Path("/some/other/dir")
    assert qty == 2
    assert overrides == {"C11": ("0R", "C21189"), "L11": ("", ""), "FL1": ("TA2429A", "C46551386")}
