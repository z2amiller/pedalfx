# Why are my parts rotated wrong at JLCPCB? (and why nobody can fully fix it)

*This came up twice recently on r/AskElectronics — once as
"[what defines 0° orientation?](https://old.reddit.com/r/AskElectronics/comments/1vi9jrv/)"
and once as
"[why do two TVS diodes from the same series show different pin 1?](https://old.reddit.com/r/AskElectronics/comments/1voy6w4/)"
— and my long answer to the second one got eaten by AutoModerator for containing
a link to a banned domain. So here's the durable version. Living copy with
deeper links lives at
[z2amiller.github.io/pedalfx/docs/jlc-rotations.html](https://z2amiller.github.io/pedalfx/docs/jlc-rotations.html).*

Disclaimer: I'm a hobbyist who went unreasonably far down this rabbit hole, not
a JLC employee. Trust but verify.

## TL;DR

- The rotation column in your CPL file is a rotation *relative to an unstated
  0°*. Your EDA tool and the assembly house don't agree on what 0° is, and
  nothing in the file tells either side.
- This is not a JLC bug and it's not new. It's the industry's oldest dirty
  secret; JLC just made it visible by selling 5 assembled boards for $20 instead
  of a 5,000-board MOQ that came with an engineer who quietly fixed your
  rotations by hand.
- JLC's DFM/placement preview is authoritative for what *their* line will do.
  Fix rotations there (or in your export tool), tick "confirm production file,"
  and put a pin-1 / polarity mark on your silkscreen so a human can catch what
  the software can't.
- Two-pin polarized parts (diodes especially, tantalums dangerously) are the
  worst case, because "pin 1" itself isn't standardized. Sometimes they come out
  right by accident. Details below.

## The problem in one paragraph

A pick-and-place file has X, Y, rotation, side. That's it — no pad geometry, no
pin numbers, no polarity. "Rotation 90" only means something if both parties
agree what the part looks like at rotation 0. Your KiCad footprint has an origin
and a pin-1 location that some library contributor chose. JLC's machine has the
part on a reel, in whatever orientation the manufacturer taped it. The
correction between the two is a property of *the pair* (this footprint, this
reel), and there is no channel in the CPL to communicate it. So every tool that
"fixes" rotations — including JLC's own preview and the community regex tables —
is really encoding a guess about both sides.

## Two standards that don't meet in the middle

There *are* standards; the problem is they cover different halves.

**On the EDA side**, IPC-7351 defines a "zero orientation" for footprints — pin
1 upper-left, pins counted counter-clockwise — and IEC 61188-7 defines its own,
which doesn't fully agree with IPC's, because of course it doesn't. KiCad's
library conventions mostly follow IPC. Mostly. Footprints from Ultra Librarian,
SnapEDA, or the manufacturer follow whatever they follow.

**On the reel side**, EIA-481 says how parts sit in tape: rectangular bodies
long-axis-perpendicular to the feed *if they fit the tape width*, parallel if
they don't; pin 1 / A1 in a defined quadrant. Because tape comes in 8/12/16/24
mm, this creates discrete thresholds — which is why the "empirical" corrections
cluster in families: SOICs and TSSOPs are always ~90° off, small chip parts are
0°, polarized caps flip from 0° to 180° right around the 8→12 mm tape boundary.
And EIA-481 explicitly notes SOT-23 has no distinguishable pin-1 mark, so it's a
per-manufacturer free-for-all. (Ask anyone who's had a SOT-23 come back 90° off.
Or three tables on my disk that say SOT-23 needs -90, 180, and
180-but-different-for-that-reel.)

Even if both standards were followed perfectly, you'd still need to know *which*
conventions your specific footprint and your specific reel follow. Nothing in
your CPL says.

## One company, one pile of metadata

LCSC (the parts distributor), JLCPCB (the fab), and EasyEDA (the EDA tool) are
the same company. Most in-stock LCSC parts — not all; roughly a third have
nothing, see the numbers below — have an EasyEDA symbol, footprint and (usually)
3D model, made by the same library team. The
[EasyEDA Footprint Naming Rule Reference](https://docs.easyeda.com/en/PCBLib/PCBLib-Naming-Rule/index.html)
— an 84-page PDF jointly written by LCSC's engineering department and the
EasyEDA team — describes how those footprints are named, and the names encode
orientation.

I can't prove it, but I'm about as sure as I can be that the DFM preview you see
after uploading is rendering the EasyEDA footprint/3D model for each LCSC
number, and that the pin-1 dot it shows you is *EasyEDA's* pin 1. Why would they
build a second library? Everything I've checked lines up with this, including
the TVS-diode mystery below.

## Reading the naming rule and the API yourself

You don't need any tool for this. Take an LCSC number and open:

```
https://easyeda.com/api/products/C5453/components
```

Pretty-print the JSON (Firefox does it natively; Chrome with any JSON viewer).
Look at:

- `packageDetail.title` — the footprint name, e.g.
  `SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL`. Read it as: 8-pin SOIC, body 4.9 × 3.9 mm,
  1.27 mm pitch, 6.0 mm lead span, and **pin 1 Bottom-Left**. The orientation
  tokens are `-TL/-TR/-BL/-BR` (pin-1 corner) or `-L/-R/-T/-B` (single-axis) for
  ICs, and `-FD/-RD/-BI` (forward / reverse / bidirectional) for two-pin
  polarized parts.
- `packageDetail.uuid` — the footprint's ID. Hundreds of thousands of parts
  share a few tens of thousands of these; parts sharing a footprint UUID need
  the same correction (see the numbers section).
- `dataStr.shape` — the *schematic symbol*, as EasyEDA's tilde-delimited SVG-ish
  drawing commands. Entries starting `P~show~0~<pin number>…` are pins, and
  *sometimes* buried in each is a label text like `~A~` or `~K~` telling you
  which pin number the library thinks is anode vs cathode. Sadly it's not
  reliable: plenty of diode symbols have no A/K text at all, and you have to
  read the *graphics* — which pin the triangle points at in the symbol, or the
  `+`/`-` marks (in different colours) drawn on the footprint in
  `packageDetail.dataStr`. Text annotations are a hint, not the answer.

The LCSC part-detail page (search the part number on their site) renders that
same symbol and footprint as SVGs, so the easiest way to "read the graphics" is
to just look at it there.

Two caveats. First, only standardized package families carry the orientation
tokens; connectors, relays, modules and the like tend to use the MPN as the
"suffix" and tell you nothing. Second, JLC's line uses this data; *you* still
have to know where pin 1 is on *your* footprint to compute the correction.
There's no escaping that.

## Worked example: two TVS diodes, same series, different pin 1

From the second Reddit thread. Two Vishay SMF-package TVS diodes, D1 =
VTVS17ASMF (C1978115) and D2 = VTVS12ASMF (C1856655), both placed at -90° in
KiCad, both with pin 1 = anode on the KiCad footprint. JLC's preview marked pin
1 on the cathode of D1 and the anode of D2. Same manufacturer, same series, same
datasheet, which says pin 1 is the anode. What?

Pull the API for both:

| LCSC     | MPN              | EasyEDA footprint          | pin 1 is |
| -------- | ---------------- | -------------------------- | -------- |
| C1978115 | VTVS17ASMF-M3-08 | `SMF_L2.8-W1.8-LS3.7-RD`   | K        |
| C1856655 | VTVS12ASMF-M3-08 | `SMF_L2.8-W1.8-LS3.7-FD-1` | A        |

(For the 12V part the symbol has literal `A`/`K` pin labels; for the 17V part it
doesn't, and you have to see that the diode symbol points at pin 1 — the
SVG-graphics problem from the previous section.) Different EasyEDA library
entries. The 17V one is drawn as "reverse direction" with pin 1 = cathode; the
12V one is "forward direction" with pin 1 = anode. Both are electrically
self-consistent — RD + K-is-pin-1 places the cathode on the same physical side
as FD + A-is-pin-1. So after your -90° both diodes come out with the anode where
you wanted it, and the board works. **But the pink pin-1 dot lands on opposite
ends**, because that dot is EasyEDA's/tape's pin 1, not yours.

This is what I mean by "correct on accident." The board is right, but only
because two errors cancelled: the library's pin numbering is flipped *and* its
footprint direction is flipped. If you had "fixed" your KiCad footprint to match
the preview's pin-1 dot, you'd have built a backwards board. And for extra fun:
C1981006 is the *same* VTVS12ASMF on a different reel size (`-M-18` vs `-M-08`),
and it's in the library as `-RD` with pin 1 = K. Same physical part, opposite
metadata.

There's a general lesson here for KiCad users specifically: KiCad's diode and
LED footprints put pin 1 on the **cathode**; EasyEDA's `-FD` is defined with the
**anode** on the left. So for diodes, "forward direction" tends to mean 180°
relative to KiCad, while for polarized caps (both conventions put + on pin 1) it
means 0°. When you see a diode that "needs 180°," ask whether it's a rotation
difference or a pin-numbering difference. They look identical in the preview and
are not identical when you change footprints.

## Some numbers (from a crawl of the in-stock catalog, mid-2026)

- JLC's assembly-eligible catalog: ~720k parts, ~675k in stock.
- Of those, ~467k have an EasyEDA component at all. About **228k in-stock parts
  (~106k SMT, ~122k THT) return nothing from the EasyEDA API** — I'm fairly
  confident these are the ones that show up as the dreaded 2×2 grey checkerboard
  in the preview: no footprint, no model, JLC's software has nothing to render
  and their engineer is going to guess or ask.
- Those 467k parts map onto **~85.6k distinct EasyEDA footprints**, which are
  only **~48.5k distinct pad geometries**. Rotation behaviour is consistent per
  footprint UUID, which is why "fix it once per package" mostly works. The
  distribution is a slam-dunk L: **the top 350 footprints (R0603, R0805, SOT-23,
  SOIC-8…) cover half of all parts, while 73 % of footprints are used by exactly
  one part** — connectors and modules with the footprint named after the part
  ([chart](https://z2amiller.github.io/pedalfx/docs/jlc-rotations-deep-dive.html#7-crawling-the-catalog-what-the-numbers-look-like)).
- Roughly half of parts have a footprint name with a parseable orientation
  token; a geometric fallback (where's pad 1 relative to the centroid) covers
  most of the rest; ~1% are hopeless.
- Correction distribution across parts: 0° ≈ 56 %, 90° ≈ 25 %, 180° ≈ 18 %, 270°
  ≈ 1 %. If your preview shows two-thirds of your parts rotated, you're normal.

## Practical advice

1. **Use the preview.** JLC's placement/DFM viewer is the ground truth for what
   their line will do. Rotate there (space bar = 90° CCW). Their part rendering
   can be *wrong* about your intent but it's *right* about their machine.
1. **Fix it at the source once you know.** In KiCad, the
   [Bouni kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools)
   plugin has a Corrections manager (regex on footprint name → rotation/offset),
   seeded from a community table that goes back to matthewlai's JLCKicadTools.
   It's empirical and imperfect — see SOT-23 above — but once you've corrected a
   package it stays corrected.
1. **Silkscreen pin 1 and polarity, always.** JLC's engineers do look, and good
   silkscreen is what lets them catch a backwards diode.
1. **Tick "Confirm parts placement / production file."** Cheap insurance,
   especially if you have any checkerboard parts or any two-pin polarized part
   you're not sure about.
1. **When in doubt, read the API.** Thirty seconds per part, and it's the same
   data JLC's tooling is using.
1. **Be suspicious of diodes and tantalums specifically.** A backwards LED is
   dark; a backwards tantalum is a small fire.
1. **Don't "fix" a footprint's pin numbering because the preview dot disagrees
   with you** until you've worked out whether it's Scenario A (real rotation
   difference) or Scenario B (pin-numbering difference that happens to cancel).

## Further reading

- [The rabbit hole: how I worked this out](https://z2amiller.github.io/pedalfx/docs/jlc-rotations-deep-dive.html)
  — EIA-481 in detail, the naming rule, the API, the crawl, and the things that
  turned out to be wrong.
- [EasyEDA Footprint Naming Rule Reference](https://docs.easyeda.com/en/PCBLib/PCBLib-Naming-Rule/index.html)
  (PDF, MIT licensed).
- [Down the rabbit hole: footprint rotation matching](https://github.com/Bouni/kicad-jlcpcb-tools/issues/752)
  — the original breadcrumb on the Bouni tracker.
- JLC's
  [minimum spacing for SMD components](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components)
  — the other thing the preview will complain about.
- My
  [JLCPCBA getting-started notes](https://z2amiller.github.io/pedalfx/docs/JLCPCBA.html)
  and
  [pitfalls and tips](https://z2amiller.github.io/pedalfx/docs/pitfalls-and-tips.html).
