# Practical Advice for Your First PCB(s)

_This guide covers the physical side of making a board — assembly, layout, and
mechanical fit. It assumes you already have a working, verified schematic;
schematic capture and electrical checks (ERC) are their own topic._

## Design for Assembly

Think about how you will assemble this board. Will you build it yourself at home
using hand soldering, hot air, or a hotplate? Alternatively, will you use a
professional PCB Assembly (PCBA) service?

### Verify Your Footprints

The #1 reason a first board comes back unusable isn't routing — it's a wrong
footprint. Common issues include pin swaps, polarity mistakes, and incorrect pad
sizes or spacing. If using PCBA services, sometimes this gets caught in their
DFM analysis, but you can't count on that catching every mistake. Verify that
you are using the correct footprint for the part, look at the datasheet if you
have to. For standard passive components, it's enough to match the package code,
but be wary of polarized components and multi-pin components.

### PCBA

#### Keeping Prototyping Costs Low

Many designers use PCBA services such as JLCPCB. There are typically two types
of assembly: "Economic" and "Standard." For prototyping, it is best to stick
with "Economic" assembly whenever possible, as "Standard" assembly is often
significantly more expensive.

Most online cached databases of components list the assembly type, and it is a
filterable checkbox on the JLCPCB search page. "Standard" assembly is usually
triggered by components that are difficult to place or solder, such as
components with very fine pitch, or temperature-sensitive components.

#### Available Components

For PCBA, part availability drives the design. With JLCPCB specifically,
designing around their Basic/Preferred parts library avoids per-part loading
fees and "out of stock" surprises. As you are speccing and placing components,
make sure that the parts you plan to use are available in the JLCPCB library.

### Building at Home

Some packages can't be hand-soldered with a traditional iron at all — any part
whose pads aren't accessible from the side (see *Component Size and Package
Type* below). Those need hot air or a hotplate.

While these can be managed with hot air, it remains problematic because it is
difficult to verify if the pads underneath have melted properly. Hot plates are
generally more effective for these types of packages.

High-density designs are difficult to place without specialized machinery. While
stencils and hotplates assist the process, consider the physical clearance
required to reach different components when soldering.

### Component Size and Package Type

Two independent things make a part hard to assemble by hand: how small it is,
and whether you can actually reach its pads with an iron. Consider both.

**Passive size (resistors, capacitors, inductors).** These are named by a size
code. The common ones are imperial: 0805 and 0603 are a comfortable floor for
hand soldering, 0402 (1.0 mm × 0.5 mm) is doable with practice, and 0201 usually
requires a microscope. Anything smaller than 0402 should be avoided for home
soldering. Watch out for the naming ambiguity: imperial "0402" and metric "0402"
are completely different sizes, and datasheets mix the two — imperial 0402 is
the same part as metric 1005.

**Pin pitch (ICs).** For chips, the number that matters is *pitch* — the
center-to-center distance between adjacent pins. Smaller pitch means the pins
are harder to solder without bridging:

| Difficulty                     | Pin pitch | Example packages                                  |
| ------------------------------ | --------- | ------------------------------------------------- |
| Comfortable for hand soldering | ≥ 0.8 mm  | SOIC (1.27 mm), SOT-23 (0.95 mm), SOP, many TSSOP |
| Doable with practice           | 0.5 mm    | LQFP/TQFP, larger QFN                             |
| Microscope territory           | ≤ 0.4 mm  | fine-pitch QFN, µDFN, some WLCSP                  |

**Pad accessibility.** Separately from pitch, ask whether the pads are exposed
at all. Leaded packages (SOIC, SOP, QFP) have pins on the outside you can touch
with an iron. Leadless, bottom-terminal packages hide some or all of their pads
underneath — QFN and DFN thermal pads, LGA, and BGA. These can't be reliably
hand-soldered and are best left to hot air, a hotplate, or a PCBA service.

### Double-Sided Assembly

This applies whether you assemble at home or use a PCBA service, so it's worth
thinking about early.

Putting SMD parts on *both* sides of the board makes home assembly much harder:
hotplates become unusable (you can't lay a populated side down), and hot air
gets tricky because reflowing the second side can disturb the first. It also
raises PCBA fees, since fab houses charge per populated side and double sided
assembly is automatically "Standard" assembly.

The exception that stays easy: SMD on one side and hand-soldered through-hole on
the other. That combination is fine for home assembly and common in practice. If
you can keep all your SMD parts on a single side, do it.

## Design for the Real World

Your PCB will likely be part of a larger system and will need to fit inside an
enclosure. Components such as buttons, knobs, jacks, and antennas must align
with the mechanical constraints of your housing.

Use the dimension tool in your CAD software to ensure the board fits within
these constraints. If you have pre-existing mounting holes to line up with, draw
them on a user layer to ensure perfect alignment for externally facing
components.

When using knobs and jacks, consider how the board will be mounted. Avoid
protrusions that enter the enclosure from multiple dimensions simultaneously, as
this can make installation nearly impossible.

Incorporate mounting holes to secure your design to the enclosure. In some
cases, such as with guitar pedals, switches or potentiometers that protrude
through the case may provide sufficient mounting support. Use standard screw
sizes (e.g. M3) and leave keep-out copper clearance around them.

Round the corners of your PCB where possible. This improves the aesthetic and
removes sharp 90-degree edges.

## Documentation: Designing for Future You

Design your board so that a stranger could understand its operation without
referring to the CAD files. That "stranger" is often you in three months, trying
to troubleshoot or deploy an older revision.

Clear markings are essential. Label every pin of every connector (unless using a
standard interface like USB) and indicate the purpose of each header. Marking
polarity and voltage ranges is critical to prevent accidental damage to the
hardware.

Always include the board name and a version number on the silkscreen. Many
designs require several revisions; clear versioning ensures you can identify the
correct board in your parts bin.

If space permits, add status LEDs and test points. They are inexpensive and
provide immediate visual confirmation of power rails. This greatly speeds up
troubleshooting during the initial bring-up of the board.

## Follow Layout Guidelines

There are some elements in a PCB that have fairly non-negotiable layout
requirements that can trip you up.

### RF/WiFi Chips

Chips like the ESP32 or nRF24L01 require specific keep-out areas around the
antenna. Always consult the datasheet, as improper placement can severely
degrade wireless performance.

### Switching Power / SMPS

Switching Mode Power Supplies (SMPS) have strict layout requirements due to
high-frequency switching noise. Follow the manufacturer's recommended layout
precisely to ensure the supply operates efficiently and does not introduce
interference into the rest of your circuit.

### Trace Widths

The default trace width in KiCad is quite narrow (0.2 mm). That's fine for most
low-current signals, but narrower than you need for a typical first design. For
power traces, you should use wider traces to reduce resistance and voltage drop.
For high current designs (motor drives, LED drivers, etc.) you may need to use
very wide traces or even copper pours to handle the current. Use a trace width
calculator to determine the appropriate trace width for your design.

## What’s a Ground Plane, Anyway?

A ground plane is a large, continuous area of copper on a PCB layer connected to
the ground net. It provides a low-impedance return path for all signals on the
board, which significantly reduces noise and electromagnetic interference (EMI).
You should incorporate a ground plane into every PCB design; it is considered a
fundamental best practice for ensuring signal integrity, even for simple
projects.

As a sensible default, include ground pours on both sides of your board. On a
two-layer design, limit traces on the bottom layer to keep the ground plane as
unbroken as possible. Place a via near every ground pad to connect it to the
ground layers effectively -- the via provides electrical conductivity to the
bottom (or inner) plane.

A four-layer board is often only marginally more expensive than a two-layer
board for smaller designs. Consider a four-layer stack-up if routing becomes
complex; it allows for dedicated power and ground planes, which simplifies
routing and improves signal integrity.

### Bypass Capacitors

In addition to having a good ground plane, you should place small capacitors
(typically 0.1 µF) close to the power pins of every IC. These bypass capacitors
help filter out noise and provide a local energy reservoir for the IC, improving
performance and stability. Place them as close as possible to the IC's power
pins, and connect them directly to the ground plane with short traces and vias.

## Before You Order

### Run DRC (Design Rule Check)

DRC checks your board against a set of manufacturing and electrical rules and
flags anything that violates them — traces too close together, drills too small,
copper too near the board edge, unconnected nets, and so on. It's the layout
equivalent of a spell-checker: it won't tell you the design is *correct*, but it
will catch the mistakes that make a board unmanufacturable or unreliable.

Do this before you order, and ideally set it up before you start routing. Enter
your manufacturer's capabilities into KiCad's board setup — minimum trace width,
minimum clearance, minimum drill size, and minimum annular ring — so that
violations are flagged as you route, not after you've paid for the board. Fab
houses publish these numbers; JLCPCB, OSH Park, and others all have a
capabilities page. Fix every violation, or understand exactly why it's safe to
ignore, before generating your manufacturing files.

The KiCad defaults are a pretty good starting point, however - I use the
defaults for my boards and have never had a problem.

Note that there are differences between "Errors" and "Warnings" for DRC. Errors
are things that will almost certainly cause a problem, while warnings flag
things that are often cosmetic, like silkscreen over a pad. You should fix all
errors, and at least look over the warnings to make sure you aren't covering up
important on-board markings.

### Checklist

A quick tick-through before you click Order:

- [ ] **Schematic verified** and ERC run clean (see the note at the top).
- [ ] **Footprints checked** against datasheets, especially connectors,
  polarized parts, and anything multi-pin.
- [ ] **Parts available** — in stock, and in your assembler's preferred library
  if using PCBA.
- [ ] **DRC passes** with your fab's design rules loaded.
- [ ] **Board fits the enclosure** — outline, mounting holes, and externally
  facing components (jacks, knobs, switches) all check out against the case.
- [ ] **Silkscreen is useful** — board name, version number, connector/header
  labels, and polarity markings, with nothing printed over pads.
- [ ] **Power and ground** — adequate trace widths, ground pour(s) with
  stitching vias, and a bypass cap at each IC.
- [ ] **Special layout rules honored** — RF keep-outs and SMPS layout follow the
  datasheet.
- [ ] **Order a few extra boards** — they're nearly free at small quantities,
  and you'll want spares for bring-up.

## Let a Robot Check It First

Most of the checklist above can be verified automatically. This repo ships a
companion AI skill, **first-pcb-review**, that reads a `.kicad_pcb` and walks
through these recommendations for you — flagging missing mounting holes, a
fragmented ground pour, hair-thin power traces, hard-to-solder packages, absent
silkscreen, and more. It even includes an optional check for signal traces
running alongside power rails, a common source of noise.

You'll find it in this repo at `.claude/skills/first-pcb-review/`. If you open
the project in [Claude Code](https://claude.com/claude-code), the skill is
discovered automatically — just ask it to *"review my board"* or *"is this ready
to fab?"* and it will run the check and explain each finding. You can also run
the script directly, with no KiCad install required:

```bash
python3 .claude/skills/first-pcb-review/scripts/pcb_review.py your_board.kicad_pcb
```

It's a companion, not a replacement: it checks *practice*, not electrical
correctness, so you still run ERC and DRC in KiCad yourself. Think of it as a
second pair of eyes that never forgets an item on the list.
