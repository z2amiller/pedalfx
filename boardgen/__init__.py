"""Generated-board toolkit: kisch (schematic writer), netcheck (netlist verification), pcbgen (pcbnew build),
dipole_arms (antenna arm footprint text), dipole_nec (free-space NEC-2 dipole model, needs a PyNEC venv).

Boards import it via sys.path (KiCad's python has no pip):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pedalfx" / "boardgen"))
    from kisch import Schematic
"""
