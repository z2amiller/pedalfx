---
name: first-pcb-review
description: >
  Use this skill to check a KiCad PCB against first-PCB best practices — the
  layout/assembly/documentation fundamentals a beginner is most likely to miss.
  Triggers: any request to "review my board", "check my PCB", "is this ready to
  order/fab", "did I miss anything", "give my layout a once-over", or questions
  about whether a .kicad_pcb follows good practice for assembly, mechanical fit,
  silkscreen/documentation, ground pours, decoupling, or power-trace sizing. It is
  the automated companion to the "Practical Advice for Your First PCB(s)" guide.
  Use it even when the user doesn't name the guide — any "sanity-check my board
  before I send it off" request qualifies. This is a READ-ONLY skill; it never
  edits the board. For deep noise/signal-integrity review of analog boards, or for
  writing pcbnew automation, a dedicated KiCad skill is a better fit.
---

# First-PCB Review

Read-only check of a `.kicad_pcb` against the fundamentals in the *Practical
Advice for Your First PCB(s)* guide. The goal is to catch the mistakes that make
a beginner's first board come back unusable or hard to build — wrong-sized
parts, no mounting holes, missing silkscreen, a fragmented ground pour,
hair-thin power traces — **before** they pay for it.

`scripts/pcb_review.py` parses the board directly, so it works on an uploaded
file with **no KiCad install and no running KiCad**. It emits a sectioned
report; your job is to read it, and explain *why* each flagged item matters. A
beginner is here to learn the mechanism, not just collect a list of red marks.

The guide this skill checks against is bundled at `references/first_pcb.md`.
Read it when you need the exact wording of a recommendation, or want to point
the user to the relevant section for the *why* behind a flagged item.

## Workflow

1. **Run the script** on the board file:
   `python3 scripts/pcb_review.py path/to/board.kicad_pcb` Add `--no-advanced`
   to drop the noise section for a pure-beginner review.
1. **Read the report top to bottom.** It is organized to mirror the guide:
   OVERVIEW → ASSEMBLY → MECHANICAL FIT → DOCUMENTATION → POWER & GROUND →
   LAYOUT REMINDERS → BEFORE YOU ORDER → ADVANCED (noise).
1. **Translate, don't transcribe.** For each `MISS`/`CHECK`/`WARN`, tell the
   user what it means and the consequence, tied to a real number from the report
   ("your +5V rail is routed at 0.25 mm — fine for signals, but it feeds three
   ICs, so widen it to keep the voltage drop down"). Praise the `OK`s briefly so
   the review isn't all negative.
1. **Rank by impact.** Lead with things that would actually ruin the board (no
   mounting holes, a rectangular outline that won't fit the case, a ground pour
   shattered into islands) over cosmetic ones.

## What the status tags mean

- **`[OK]`** — the guide asks for this and it's present. Reassure, move on.
- **`[MISS]`** — asked for, and absent. These are the action items.
- **`[CHECK]`** — can't be decided by parsing alone; a human must eyeball it.
  Say *what* to look at and *how* to judge it, don't just repeat "check."
- **`[WARN]`** — present but likely to cause trouble (double-sided SMD, a
  leadless package on a hand-soldered board).
- **`[INFO]`** — a neutral fact (layer count, board size) for context.
- **`[n/a]`** — the check doesn't apply to this board.

## Reading each section (what the numbers mean)

- **ASSEMBLY.** Small passives (0402 = practice, 0201/smaller = microscope) and
  fine-pitch/leadless packages are flagged from footprint names and the `Pxmm`
  pitch token. `WARN` on leadless (QFN/DFN/BGA/LGA) means pads are hidden
  underneath — an iron can't reach them, so it's hot air / hotplate / PCBA only.
  Double-sided SMD is called out because it blocks a hotplate and usually forces
  the pricier "Standard" assembly tier.
- **MECHANICAL FIT.** No mounting holes is a real `MISS` unless panel hardware
  (pots/switches through the enclosure) holds the board — say so, since that
  exception is common on pedals. A rectangular outline earns a nudge to round
  the corners.
- **DOCUMENTATION.** Board name + revision on silk, test points, status LEDs,
  connector labeling. The board-name check can only match the *project
  filename*, so it prints the silk text and asks you to confirm a real name is
  present — read that line before declaring a miss. A connector counts as
  labeled if it draws its own silk — including a field like `Control` placed on
  a silk layer — or has free silk text within ~8 mm of its pads (free-labeling
  pins on the board is often clearer than footprint pin numbers). It's still a
  proxy, so treat a remaining flag as a prompt to look, not a verdict.
- **POWER & GROUND.** Pour coverage and **island count per layer** — a ground
  "plane" shattered into many islands isn't a plane; return current can't flow
  under the signal, so the loop grows and the board gets noisier. Few stitching
  vias + a fragmented pour is the bad combination. Power/ground nets routed at
  or below `--thin` are flagged to widen. Bypass caps are matched heuristically
  (a ≤1 µF cap on an IC's supply net, within 5 mm of the power pin) — label it
  as a heuristic, because a missing match can mean an unusual net name rather
  than a missing cap.
- **LAYOUT REMINDERS.** RF and switching-supply parts can't have their keep-outs
  verified by parsing, so the skill just surfaces them with a "follow the
  datasheet" reminder. Don't over-claim here.
- **BEFORE YOU ORDER.** The script can't run DRC (that needs KiCad). It checks
  for a `.kicad_dru` file and reminds the user to load their fab's rules and run
  DRC — which is also what catches silk-over-pad and clearance, so those aren't
  reimplemented here.
- **ADVANCED: NOISE COUPLING.** Off the beginner path on purpose, and **name-
  independent**: it treats *every* routed signal net as a potential victim and
  measures geometry, so it doesn't depend on any house net-naming. Aggressors
  are supply/plane nets — anything matching a power pattern, filled as a copper
  pour, or named like a clock, excluding ground. `WARN` means a signal trace
  runs broadside next to one for a real distance — the classic "input next to
  the power rail" that injects hum. **False positives are expected** (a net
  running beside its own supply is fine); present it as "verify these," not a
  rule. Only nets with a substantial alongside run (≥10 mm and ≥15% of their
  length by default) are listed. Genuinely useful on analog / mixed-signal
  boards; a solid inner-plane board will usually show nothing here. Frame it
  that way.

## Tuning for a different house style (this is a GENERIC skill)

The point of this skill (vs. a project-specific one) is that it keys off
standard KiCad conventions, not any one person's labels. When a board uses
different naming, adjust rather than misreport:

- `--power` / `--ground` — comma-separated globs for supply and ground net
  names. Defaults cover `+5V`, `VCC`, `VDD`, `GND`, `VSS`, etc. If bypass or
  trace-width checks come back `n/a`/empty, the net names probably don't match —
  widen these.
- `--thin <mm>` — the width at or below which a power/ground net is flagged
  (default 0.3). Raise it on higher-current boards.
- `--proximity <mm>` — "running alongside" distance for the noise section.
- The pattern lists at the top of `scripts/pcb_review.py` (package keywords,
  refdes prefixes for connectors/mounting holes/test points) are editable in one
  place if a board uses unusual footprints. A wrong count almost always means a
  part wasn't recognized — widen the relevant list, don't hand-wave the number.

## Boundaries

- **Read-only.** Never edit the board. Recommend changes; let the user make
  them.
- **Not a substitute for DRC or ERC.** This checks *practice*, not electrical
  correctness or manufacturability rules. Always tell the user to run KiCad's
  DRC (and that the schematic/ERC came first — the guide assumes a verified
  schematic).
- **Heuristics are heuristics.** Bypass-cap proximity, connector labeling, and
  RF/ SMPS detection are best-effort. Present them as "worth a look," and lean
  on the measured numbers (lengths, widths, island counts, pitch) which are
  exact.

## Compatibility

Standalone Python 3.9+ — no external packages, no `pcbnew`. Parses KiCad 6–9
`.kicad_pcb` files (both the numeric `(net 5)` and named `(net 5 "GND")` forms).
