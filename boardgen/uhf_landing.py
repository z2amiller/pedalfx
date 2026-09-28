"""Where the castellated UHF module (util-UHFModule, 32 x 30 mm) lands on a bare antenna board: the dummy pads under
its ground castellations, its pin-rivet holes, its pigtail cinch slot and top-edge notch, and its outline on the silk
(beads kicad-wbhj, kicad-jmp4, kicad-gpmd.2). Shared by util-Dipole1090, util-Dipole772 and util-Collinear1090 so the
landing cannot drift between boards; util-UHFModule/tools/check_landing.py checks it against the module itself.

Board frame: the module's top edge on the board's top edge (y = top), centred on the feed at x = xc; its feed
castellations sit on the arm ends on the feed line, FEED_DY below the top edge. The schematic half runs under the
system python; silk() needs KiCad's python.
"""
MOD_HW = 16.0                        # module half width (module frame x 0..32)
FEED_DY = 23.0                       # feed line below the top edge (7 mm above the bottom of a 30 mm board)
LANDING = 3.5                        # bare arm copper from each arm's inner end, under the feed castellations
GND_DY = (1.5, 16.5)                 # module GND castellations E3/E5 and E4/E6, module frame y
PIN_DX, PIN_DY = 10.6, 18.3          # module pin holes H6/H7: module frame x 5.4 / 26.6, y 18.3
CINCH_DX, CINCH_DY = 11.0, 6.1       # module cinch slot H5: module frame x 27, y 6.1
NOTCH_W, NOTCH_D = 3.5, 1.6          # top-edge notch above H5


def schematic(sch, rf):
    """Place H5, M1-M4, H6 and H7 (no nets), at the schematic positions the dipoles have always used."""
    sch.place("Mechanical:MountingHole", "H5", "pigtail cinch slot", f"{rf}:Slot_NPTH_1.8x3.5mm", 91, 70, 0, in_bom=False)
    for i in range(4):
        sch.place("Mechanical:MountingHole_Pad", f"M{i+1}", "module GND landing", f"{rf}:DummyPad_1.8", 100 + 15.24 * i, 70, 0,
                  in_bom=False)
        sch.no_connect((f"M{i+1}", 1))
    for i in (6, 7):                 # under the module's H6/H7: a wire soldered through both boards
        sch.place("Mechanical:MountingHole_Pad", f"H{i}", "pin rivet", f"{rf}:PinRivet_D1.0_P1.8", 100 + 15.24 * (i - 2), 70, 0,
                  in_bom=False)
        sch.no_connect((f"H{i}", 1))


def place(xc, top):
    """{ref: (x, y, rotation)} for the landing parts on a board whose top edge is y = top."""
    y1, y2 = top + GND_DY[0], top + GND_DY[1]
    return {"M1": (xc - MOD_HW, y1, 0), "M2": (xc - MOD_HW, y2, 0), "M3": (xc + MOD_HW, y1, 0), "M4": (xc + MOD_HW, y2, 0),
            "H6": (xc - PIN_DX, top + PIN_DY, 0), "H7": (xc + PIN_DX, top + PIN_DY, 0),
            "H5": (xc + CINCH_DX, top + CINCH_DY, 90)}


def top_notch(xc):
    """(x, width, depth) of the cinch notch, for pcbgen's rounded_outline top_notches."""
    return (xc + CINCH_DX, NOTCH_W, NOTCH_D)


def silk(brd, xc, top, bottom, arm_hw):
    """The module outline on the front silk, broken around the dummy pads and the bare arm copper, and 'module'."""
    import pcbnew
    from pcbgen import MM, V
    y1, y2, yf = top + GND_DY[0], top + GND_DY[1], top + FEED_DY
    for x in (xc - MOD_HW, xc + MOD_HW):
        for a, b in ((top + 0.5, y1 - 1.4), (y1 + 1.4, y2 - 1.4), (y2 + 1.4, yf - arm_hw - 0.8), (yf + arm_hw + 0.8, bottom - 0.5)):
            if b - a >= 1.0:                          # skip stubs (y1 sits 1.5 mm from the top edge)
                s = pcbnew.PCB_SHAPE(brd.board)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(V(x, a)); s.SetEnd(V(x, b))
                s.SetLayer(pcbnew.F_SilkS); s.SetWidth(MM(0.15)); brd.board.Add(s)
    brd.text("module", xc, top + 7.0, pcbnew.F_SilkS, 1.0)
