# mn3102-dropin — CD4047B replacement for the MN3102 BBD clock driver

Replaces the Panasonic MN3102 (clock generator for MN3204/05/07/08/09 BBDs) with
a CD4047B plus four passives. Two ways to use it:

## 1. As a schematic block in a new design

Add `clock_3102_cd4047.kicad_sch` as a hierarchical sheet wherever a host
schematic shows an MN3102. The 8 sheet pins mirror the MN3102's DIP-8 pins
one-for-one:

| Sheet pin | MN3102 pin | Role                                           |
| --------- | ---------- | ---------------------------------------------- |
| VDD       | 1          | 4–10V supply (feed from the filtered BBD rail) |
| CP1       | 2          | Clock out (4047 Q)                             |
| GND       | 3          | Ground                                         |
| CP2       | 4          | Clock out, antiphase (4047 Q̄)                  |
| OX3       | 5          | C-drive (4047 pin 1) — timing cap OX3→OX1      |
| OX2       | 6          | R-drive (4047 pin 2) — timing resistor OX2→OX1 |
| OX1       | 7          | RC common / oscillator input (4047 pin 3)      |
| VGG_OUT   | 8          | 15/16·VDD (≈14/15) for the BBD's VGG pin       |

Wire the host's existing timing R, C, and LFO network to OX1/OX2/OX3 exactly as
they were wired to the MN3102. Both self-oscillation (R + C) and current-driven
hosts (Julia/Caesar/PizzaPizza style: OX2 open, LFO current into OX1) work
unchanged. f_CP = 1/(4.4·R·C) at 50% duty.

## 2. As a DIP-8 adapter board

The root sheet (`fx-MN3102DropIn.kicad_sch`) adds J1, a DIP-8 machined-pin
header footprint, so the same block can be laid out as a tiny board that plugs
into an existing MN3102 socket.

### Package fit inside the DIP-8 outline

The DIP-8 pad ring's inner edge is 3.01mm from the board centerline (pads Ø1.6
on 7.62mm rows). Measured pad-field extents (KiCad footprints):

| Package                                  | Pad field half-extent        | Fits between rows?                   |
| ---------------------------------------- | ---------------------------- | ------------------------------------ |
| SOIC-14 (leads across)                   | 3.45mm                       | **No — overlaps DIP pads by 0.44mm** |
| TSSOP-14 rotated 90° (leads along board) | 2.15mm across / 3.60mm along | **Yes, ≥0.5mm clear**                |

**Recommended construction: everything on top, bare bottom.** Board ~12.7mm
long: TSSOP-14 rotated 90° in the middle between the pin rows, two 0603s on each
end tongue (~2.5mm overhang past the socket ends). Bare bottom = the board seats
flush on the socket, no standoff/height concerns at all.

Overhang clearance, verified against fx-PizzaPizza: nearest on-axis parts are
R9/R11 (0603, ~0.8mm tall) 3.4mm past one socket end — the overhang flies ~3.5mm
above them at socket-top height; the other end is clear for 8mm+. In general
only tall neighbors matter (electrolytics, box film caps, adjacent socketed ICs)
— check per host, especially through-hole builds.

Alternate (zero overhang): passives on the underside between the pin rows — then
use collared machined-pin strips (≥1.5mm standoff) so back-side parts (≤0.9mm
with solder) clear the socket face.

VGG cap note: C2 is optional insurance, not functional — the BBD's VGG pin draws
no DC current and many hosts already have a cap on that net (PizzaPizza: C21
22µF). 100nF is plenty (filter corner ~1.7kHz vs 50-200kHz clock); DNP it if
space is tight. Lowest-profile alternates, all Basic tier 0402: 1k C11702, 15k
C25756, 100nF 50V C307331 (~0.55mm tall).

## BOM (JLC, snapshot 2026-08)

| Ref | Value                | Package  | LCSC     | Tier     |
| --- | -------------------- | -------- | -------- | -------- |
| U1  | CD4047BPWR (adapter) | TSSOP-14 | C2652491 | Extended |
| R1  | 1k                   | 0603     | C21190   | Basic    |
| R2  | 15k                  | 0603     | C22809   | Basic    |
| C1  | 100n                 | 0603     | C14663   | Basic    |
| C2  | 100n (optional)      | 0603     | C14663   | Basic    |

**U1 sourcing reality** (live-checked 2026-08-08): the TSSOP-14 CD4047BPWR is
out of stock at JLC/LCSC (global-sourcing/notify-me only), but Mouser/DigiKey
stock it (~$0.30-0.60). Adapter plan: have JLC assemble the four Basic passives,
hand-stencil the TSSOP at home. For **in-design use** (full pedal board, no size
constraint), swap U1's footprint to SOIC-14 and use **CD4047BM96, LCSC C46538**
(35k+ stock) for normal JLC assembly.

Do **not** substitute 74HC4047 (6V max). CD4047B/HEF4047B only. Timing cap in
the host must be C0G/NP0.

Full design rationale, datasheet references, and caveats (clock cross-point,
drive limits for 4096-stage BBDs): `~/Claude/cd4047-mn3102-clock-reference.md`.
Verification: ERC 0/0, netlist checked against golden connectivity map
(kicad-cli 10.0.4).
