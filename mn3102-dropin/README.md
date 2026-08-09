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
into an existing MN3102 socket. SOIC-14 fits between the 7.62mm pin rows;
passives go on the underside.

## BOM (JLC, snapshot 2026-08)

| Ref | Value      | Package | LCSC   | Tier     |
| --- | ---------- | ------- | ------ | -------- |
| U1  | CD4047BM96 | SOIC-14 | C46538 | Extended |
| R1  | 1k         | 0603    | C21190 | Basic    |
| R2  | 15k        | 0603    | C22809 | Basic    |
| C1  | 100n       | 0603    | C14663 | Basic    |
| C2  | 1u         | 0805    | C28323 | Basic    |

Do **not** substitute 74HC4047 (6V max). CD4047B/HEF4047B only. Timing cap in
the host must be C0G/NP0.

Full design rationale, datasheet references, and caveats (clock cross-point,
drive limits for 4096-stage BBDs): `~/Claude/cd4047-mn3102-clock-reference.md`.
Verification: ERC 0/0, netlist checked against golden connectivity map
(kicad-cli 10.0.4).
