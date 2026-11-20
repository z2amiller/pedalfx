"""Single source of truth for the Full1590XXTemplate coordinates.

Spec: ~/Claude/docs/superpowers/specs/2026-11-19-1590xx-template-design.md. Board coordinates are fx-L7's (mm,
KiCad y down); the enclosure centre is (147.5, 100.75) and a Tayda face-A point (X, Y) sits at board
(147.5 - Y, 100.75 + X). Tayda +X points at the footswitches, +Y is the player's right. Stdlib only, so both the
stdlib stages and KiCad's bundled python import it.
"""

CENTRE = (147.5, 100.75)


def tayda_to_board(x: float, y: float) -> tuple:
    return (round(CENTRE[0] - y, 4), round(CENTRE[1] + x, 4))


POT_ROWS_X = (-38.0, -12.7)                     # L7 Tayda file
POT_COLS_Y = (-55.0, -33.0, -11.0, 11.0, 33.0, 55.0)
ROW3_X, ROW3_Y = 13.0, (-55.0, -11.0, 11.0, 55.0)
SWITCH_X_TAYDA, SWITCH_TAYDA_Y = 45.0, (-38.0, 0.0, 38.0)   # L7's +/-38 plus the new centre
LED_X_TAYDA = 27.4                              # fleet "LED above footswitch": 17.6 mm north of the switch

GUIDES = []                                     # (label, board_x, board_y, diameter)
for _row, _x in enumerate(POT_ROWS_X, 1):
    for _y in POT_COLS_Y:
        GUIDES.append((f"POT ROW {_row} Y{_y:+g}", *tayda_to_board(_x, _y), 8.2))
for _y in ROW3_Y:
    GUIDES.append((f"ROW 3 Y{_y:+g}", *tayda_to_board(ROW3_X, _y), 8.2))
for _y in SWITCH_TAYDA_Y:
    GUIDES.append((f"FOOTSWITCH Y{_y:+g}", *tayda_to_board(SWITCH_X_TAYDA, _y), 12.4))
for _y in SWITCH_TAYDA_Y:
    GUIDES.append((f"LED Y{_y:+g}", *tayda_to_board(LED_X_TAYDA, _y), 5.2))

SWITCH_X = tuple(tayda_to_board(SWITCH_X_TAYDA, y)[0] for y in SWITCH_TAYDA_Y)   # (185.5, 147.5, 109.5)
SWITCH_Y = tayda_to_board(SWITCH_X_TAYDA, 0.0)[1]                                 # 145.75
LED_Y = tayda_to_board(LED_X_TAYDA, 0.0)[1]                                       # 128.15

# Tiny footswitch board (util-TinyFootSwitch): header J4 row 12.72 mm north of the switch centre (B2), header centre
# 0.225 mm EAST of it (J4 centre 110.025, B2 109.8). Both boards run JACK_IN..JACK_OUT west to east in their own
# views, so the main board takes the Tiny's offset unmirrored. (Full125's and fx-Electro's J101s sit ~0.45 mm west of
# this; the fx-Electro spec lists the nudge east as a follow-up.)
TINY_HEADER_DY, HEADER_DX, PITCH, PINS = 12.72, 0.225, 2.54, 8
HEADER_Y = round(SWITCH_Y - TINY_HEADER_DY, 4)                                    # 133.03
HEADER_PAD = 1.7
TINY_BOX = (-9.95, -14.72, 9.95, 8.53)    # Tiny outline about the switch centre, x widened to the larger side
SW_COURTYARD_Y = 8.5                      # Alpha_3PDT courtyard half-height
LED_FLANGE_R = 2.9                        # 5 mm LED flange
TOGGLE_BOX = (-4.25, -6.5, 4.25, 6.5)     # generous mini-toggle body about a row-3 guide


def header_pin1(switch_x: float) -> tuple:
    centre = switch_x + HEADER_DX
    return (round(centre - PITCH * (PINS - 1) / 2, 4), HEADER_Y)


BOTTOM_Y = 135.0
OUTLINE_BBOX = (81.05, 215.05, 42.95, BOTTOM_Y)             # xmin, xmax, ymin, ymax
SIDE_END_Y = 134.0                                          # side edges stop here, 1 mm corner to the bottom

# Side C (the top wall) on L7's Tayda file: jacks Ø 12.8 at Y +38 (input) and -38 (output); the DC hole is a
# rectangle Y -5..+5 (and side-C x -9.3..2.9, 12.2 mm tall). Drawn at their board x, centred on the top edge.
TOP_Y = OUTLINE_BBOX[2]
for _y, _name in ((38.0, "INPUT"), (-38.0, "OUTPUT")):
    GUIDES.append((f"{_name} JACK side C Y{_y:+g}", tayda_to_board(0.0, _y)[0], TOP_Y, 12.8))
DC_GUIDE = (CENTRE[0] - 5.0, TOP_Y - 6.1, CENTRE[0] + 5.0, TOP_Y + 6.1)     # x0, y0, x1, y1

# ref -> (x, y, rot, layer); D102 is its BODY CENTRE (pad 1 is 1.27 mm east at rot 180 on B.Cu)
FOOTPRINTS = {
    "J102": (102.06824, 61.741142, 90, "F.Cu"),     # input jack, L7's J5
    "J103": (177.135, 62.0, 90, "F.Cu"),            # output jack, L7's J3
    "J104": (147.5, 53.6, 180, "F.Cu"),             # DC jack, L7's J4
    "J101": (*header_pin1(SWITCH_X[0]), 90, "F.Cu"),   # bypass header at L7's bypass switch (Tayda Y -38)
    "BP101": (151.05, 57.25, 0, "F.Cu"),            # J104 + (3.55, 3.65), as on BlueBlood and fx-Electro
    "D102": (SWITCH_X[0], LED_Y, 180, "B.Cu"),
}
LED_PAD1_DX = 1.27
REMOVED = ("D101", "R101", "L101", "C101")
CLEAR = {"tiny_pillar": 5.0, "courtyard_edge": 2.0, "pad_edge": 0.5, "led_header": 1.0, "led_toggle": 2.0}
