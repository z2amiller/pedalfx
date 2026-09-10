"""Shared TQP3M9036 LNA block and coax bias tee for the antenna boards (bead kicad-mdsv).

Schematic (kisch) and board (pcbgen) halves of one block, reused by the 772 / 1090 / VHF boards with only the
DC-block and choke values changing. The block is the 772 board's C8/U1/C9/R3/L9 + L10/C10/C17/D2/TP1 as drawn
(util-Antenna772/tools/gen_772.py, gen_772_board.py); the reference names are fixed so the boards' netlist checks
and silk stay alike.

Circuit: RF in -> C8 (DC block) -> U1 TQP3M9036 pin 2, pin 7 -> C9 (DC block) -> RF out; L9 (RF choke) from pin 7
to the BIAS rail; R3 10k from pin 6 (shutdown) to ground; pins 1/3/4/5/8/9 ground. Bias tee: L10 from the coax
side of the output to BIAS, C10 100 n + C17 100 p decoupling, D2 SMF5.0A TVS, TP1 test pad. 5 V arrives on the
coax from the indoor USB bias-tee injector (no dropper, no LDO: TQP3M9036 is 3.3-5.25 V, 68 mA at 5 V).

Board floorplan (all on the front face, chain running LEFTWARDS along the RF row y=ra, as on the 772 board):
  C8 at (xr, ra)  U1 at (xr-3.2, ra-0.25)  C9 at (xr-6.6, ra)  R3 above U1  L9 over C9's LNA_OUT pad.
  Bias tee: L10 vertical at (xb, yb) tapping the RF_OUT lane below it, TP1 / C10 / C17 / D2 to its right.
"""

# ---- values -----------------------------------------------------------------------------------------
FP_0603 = {"C": "Capacitor_SMD:C_0603_1608Metric", "L": "Inductor_SMD:L_0603_1608Metric", "R": "Resistor_SMD:R_0603_1608Metric"}
TQP_FP = "Package_DFN_QFN:DFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.6mm"
TQP_LCSC = "C920261"
CHOKE_150N = ("150n", "C113131")          # LQW18ANR15G00D, 772 and 1090 boards
BLOCK_1N = ("1n", "C1588")                # 772 (and VHF)
BLOCK_100P = ("100p", "C14858")           # 1090


# ---- schematic -------------------------------------------------------------------------------------
def lna_block(sch, x0, y, *, block=BLOCK_1N, choke=CHOKE_150N, dnp=False, rf="RF_Antenna", fp=FP_0603):
    """Draw C8 -> U1 -> C9 with R3 and L9. The RF input node is (x0, y) (the caller wires to it); returns
    {"in": (x0, y), "out": (x0+43, y), "bias": (x0+29, y-15.24)} where "bias" is the top of L9 (BIAS rail)."""
    tag = " (DNP)" if dnp else ""
    sch.place("Device:C", "C8", block[0] + tag, fp["C"], x0 + 5, y, 90, fields={"LCSC": block[1]}, dnp=dnp)
    sch.wire((x0, y), ("C8", 1))
    sch.place(f"{rf}:TQP3M9036", "U1", "TQP3M9036" + tag, TQP_FP, x0 + 19, y, 0,
              fields={"LCSC": TQP_LCSC}, dnp=dnp, ref_off=(-2.54, -7.62), val_off=(-11.43, 8.89))
    sch.wire(("C8", 2), ("U1", 2)); sch.gnd(("U1", 9))
    sch.place("Device:R", "R3", "10k" + tag, fp["R"], x0 + 16.54, y + 12.7, 0, fields={"LCSC": "C25804"}, dnp=dnp,
              ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
    sch.wire(("U1", 6), ("R3", 1)); sch.gnd(("R3", 2)); sch.label("SD", (x0 + 16.54, y + 8.89), rot=90)
    sch.label("LNA_IN", (x0 + 9.5, y))
    sch.place("Device:C", "C9", block[0] + tag, fp["C"], x0 + 35, y, 90, fields={"LCSC": block[1]}, dnp=dnp)
    sch.wire(("U1", 7), (x0 + 29, y), ("C9", 1))
    sch.label("LNA_OUT", (x0 + 27.5, y))
    sch.place("Device:L", "L9", choke[0] + tag, fp["L"], x0 + 29, y - 7.62, 0, fields={"LCSC": choke[1]}, dnp=dnp,
              ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
    sch.wire((x0 + 29, y), ("L9", 2)); sch.wire(("L9", 1), (x0 + 29, y - 15.24))
    sch.wire(("C9", 2), (x0 + 43, y))
    return {"in": (x0, y), "out": (x0 + 43, y), "bias": (x0 + 29, y - 15.24)}


def bias_tee(sch, x, y, *, choke=CHOKE_150N, dnp=False, fp=FP_0603):
    """L10 tapping the RF_OUT node at (x, y) up to the BIAS rail at y-15.24, then C10, C17, D2, TP1 along the rail.
    Returns {"rf": (x, y), "bias": (x, y-15.24), "bias_end": (x+22, y-15.24)}; the caller wires the rail."""
    tag = " (DNP)" if dnp else ""
    yb = y - 15.24
    sch.place("Device:L", "L10", choke[0] + tag, fp["L"], x, y - 7.62, 0, fields={"LCSC": choke[1]}, dnp=dnp,
              ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
    sch.wire((x, y), ("L10", 2)); sch.wire(("L10", 1), (x, yb))
    sch.wire((x, yb), (x + 22, yb))
    sch.place("Device:C", "C10", "100n" + tag, fp["C"], x + 5, y - 10.16, 0, fields={"LCSC": "C14663"}, dnp=dnp)
    sch.wire((x + 5, yb), ("C10", 1)); sch.gnd(("C10", 2))
    sch.place("Device:C", "C17", "100p" + tag, fp["C"], x + 11, y - 10.16, 0, fields={"LCSC": "C14858"}, dnp=dnp)
    sch.wire((x + 11, yb), ("C17", 1)); sch.gnd(("C17", 2))
    sch.place("Device:D_Zener", "D2", "SMF5.0A" + tag, "Diode_SMD:D_SOD-123F", x + 17, y - 10.16, 270,
              fields={"LCSC": "C19077497"}, dnp=dnp, ref_off=(5.5, -1.27), val_off=(5.5, 1.27))
    sch.wire((x + 17, yb), ("D2", 1)); sch.gnd(("D2", 2))
    sch.place("Connector:TestPoint", "TP1", "BIAS 5V", "TestPoint:TestPoint_Pad_2.0x2.0mm", x + 22, y - 20.32, 0,
              in_bom=False, dnp=dnp, ref_off=(1.27, -1.27), val_off=(1.27, 1.27))
    sch.wire((x + 22, yb), ("TP1", 1))
    return {"rf": (x, y), "bias": (x, yb), "bias_end": (x + 22, yb)}


# expected-net fragments for netcheck (merge into the board's EXPECTED table)
LNA_NETS = {
    "LNA_IN": {"C8.2", "U1.2"},
    "LNA_OUT": {"U1.7", "C9.1", "L9.2"},
    "SD": {"U1.6", "R3.1"},
}
LNA_GND = {"U1.1", "U1.3", "U1.4", "U1.5", "U1.8", "U1.9", "R3.2"}
TEE_BIAS = {"L9.1", "L10.1", "C10.1", "C17.1", "D2.1", "TP1.1"}
TEE_GND = {"C10.2", "C17.2", "D2.2"}


# ---- board -------------------------------------------------------------------------------------------
def lna_place(xr, ra, in_net):
    """PLACE-table entries for the block with C8 at (xr, ra) and the chain running leftwards along y=ra.
    in_net is the net on C8's right pad ("/RF_FILT" on the 772 and 1090 boards)."""
    return {
        "C8": (xr, ra, 0, (in_net, "R")),
        "U1": (xr - 3.2, ra - 0.25, 0, ("/LNA_IN", "R")),      # after the 180 flip (pin 2 right) pins 2/7 sit on y=ra
        "C9": (xr - 6.6, ra, 0, ("/LNA_OUT", "R")),
        "R3": (xr - 3.0, ra - 2.7, 0, ("/SD", "L")),           # shutdown pull-down above U1 (room for the BIAS via beside L9)
        "L9": (xr - 6.0, ra - 2.5, 90, ("/LNA_OUT", "D")),     # supply choke, its LNA_OUT pad over C9's
    }


def tee_place(xb, yb):
    """PLACE-table entries for the bias tee with L10 vertical at (xb, yb), its BIAS pad downwards (the RF_OUT
    lane runs above it)."""
    return {
        "L10": (xb, yb, 90, ("/BIAS", "D")),
        "TP1": (xb - 3.0, yb + 3.4, 0, None),
        "C10": (xb + 3.4, yb + 2.2, 0, ("/BIAS", "L")),
        "C17": (xb + 3.4, yb + 4.4, 0, ("/BIAS", "L")),
        "D2": (xb + 5.6, yb - 0.4, 0, ("/BIAS", "L")),
    }


def lna_route(brd, ra, F):
    """Route inside the block: C8 -> U1 pin 2, pin 7 -> C9, pin 6 -> R3, L9 onto C9's LNA_OUT pad.
    Returns (c8_in_pad, c9_out_pad, l9_bias_pad) for the caller's chain and BIAS routing."""
    PN, track = brd.pad_by_net, brd.track
    in_net = [n for n in (brd.pad_net.get(("C8", "1")), brd.pad_net.get(("C8", "2"))) if n != "/LNA_IN"][0]
    out_net = [n for n in (brd.pad_net.get(("C9", "1")), brd.pad_net.get(("C9", "2"))) if n != "/LNA_OUT"][0]
    c8r, c8l = PN("C8", in_net), PN("C8", "/LNA_IN")
    u_in, u_out = PN("U1", "/LNA_IN"), PN("U1", "/LNA_OUT")
    assert abs(u_in[1] - ra) < 0.01 and abs(u_out[1] - ra) < 0.01, f"U1 RF pins off the RF row: {u_in} {u_out}"
    track("/LNA_IN", F, 0.5, c8l, (u_in[0] + 0.9, ra))
    track("/LNA_IN", F, 0.3, (u_in[0] + 0.9, ra), u_in)
    c9r, c9l = PN("C9", "/LNA_OUT"), PN("C9", out_net)
    track("/LNA_OUT", F, 0.3, u_out, c9r)
    # shutdown pin 6 (above pin 7 in this orientation): out to the left, up beside U1, into R3
    sd, r3a = PN("U1", "/SD"), PN("R3", "/SD")
    assert sd[1] < u_out[1], f"expected pin 6 above pin 7: {sd} {u_out}"
    track("/SD", F, 0.25, sd, (u_out[0] - 0.9, sd[1]), (u_out[0] - 0.9, r3a[1] + 0.6), (r3a[0], r3a[1] + 0.6), r3a)
    # supply choke: its LNA_OUT pad drops straight down into C9's LNA_OUT pad
    l9o, l9b = PN("L9", "/LNA_OUT"), PN("L9", "/BIAS")
    assert abs(l9o[0] - c9r[0]) < 0.4, f"L9 must sit over C9's LNA_OUT pad: {l9o} {c9r}"
    track("/LNA_OUT", F, 0.4, l9o, (l9o[0], ra))
    # exposed paddle: one ground via in the middle of pad 9
    ep = brd.pad_xy("U1", 9)
    brd.via("GND", ep[0], ep[1], drill=0.3, dia=0.6)
    return c8r, c9l, l9b


def tee_route(brd, yb, F, rf_net="/RF_OUT"):
    """Route the bias tee on the front: TP1, C10, C17, D2 off L10's BIAS pad along y=yb+2.2.
    Returns (l10_rf_pad, l10_bias_pad); the caller joins the RF pad to the RF_OUT lane and the BIAS pad to L9."""
    PN, track = brd.pad_by_net, brd.track
    l10o, l10b = PN("L10", rf_net), PN("L10", "/BIAS")
    tp1 = PN("TP1", "/BIAS")
    c10b, c17b, d2b = PN("C10", "/BIAS"), PN("C17", "/BIAS"), PN("D2", "/BIAS")
    yl = yb + 2.2
    track("/BIAS", F, 0.5, l10b, (l10b[0], yl), (c10b[0], yl), c10b)
    track("/BIAS", F, 0.5, (c10b[0], yl), (c10b[0], c17b[1]), c17b)
    track("/BIAS", F, 0.5, (c10b[0], yl), (c10b[0], d2b[1]), d2b)
    track("/BIAS", F, 0.5, (l10b[0], yl), (tp1[0], yl), tp1)
    return l10o, l10b
