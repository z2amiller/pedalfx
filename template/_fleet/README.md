# pedal-fleet

Keeps every KiCad template in `pedalfx/template/` and every board under
`~/Documents/repos` on the shared fleet kit in [`kit/`](kit/README.md): DRC
rules, text defaults and component classes.

```
cd ~/Documents/repos/pedalfx/template/_fleet
uv run pedal-fleet check --all              # read-only drift + outline report, exit 1 on either
uv run pedal-fleet apply --templates        # stamp the kit into the templates
uv run pedal-fleet apply --boards --commit  # retrofit the fleet, one commit per repo, no push
uv run pedal-fleet apply fx-Foo --dry-run   # show the diff for one project
uv run pedal-fleet drc --templates --fail-on error
uv run pedal-fleet drc fx-Foo --save before.json   # later: --baseline before.json
uv run pedal-fleet new-template Name --from ~/Documents/repos/fx-Foo --title "..." --description "..."
uv run pedal-fleet clone util-Bar --from ~/Documents/repos/util-Foo --status utility --note "..." --github public
uv run pedal-fleet silk-labels fx-Foo --dry-run    # plan reference-label moves; drop --dry-run to write
uv run pedal-fleet outline --all                   # board outlines: micro-gaps, stubs, exact closure
uv run pedal-fleet outline fx-Foo --dry-run        # show the heal as a diff; --fix writes it
```

Targets are project directories or `.kicad_pro` files, or `--templates`,
`--boards`, `--all`.

`apply` refuses to run while any KiCad process is running (`--force` overrides
that, but never a project whose lock file exists), patches
`board.design_settings.defaults` and `component_class_settings` in the project
file, splices the fleet block into `<name>.kicad_dru` (rules outside the markers
are kept and win), and writes `.gitignore` (always for templates, only when
missing for boards). `--prune-exclusions` drops DRC exclusions the kit makes
redundant. `--validate` runs a probe rule through kicad-cli, because kicad-cli
ignores an unparsable rules file silently.

Tests: `uv run pytest -q` (kicad-cli integration tests skip when it is not
installed).

`clone` copies a board's working files (project, board, every sheet, rules, lib
tables, `jlcpcb/project.db`, `.gitignore`) into `<repos>/<name>`, renames the
project everywhere KiCad embeds it (project-file meta, each sheet's
symbol-instance `project` entries, the board's `sheetfile` entries), leaves
title blocks and silk alone (it lists any file that still mentions the old
name), applies the kit, verifies the rename with a kicad-cli netlist export, and
makes the initial commit on `main`. `--status`/`--note` set the clone's own
`BOARD_STATUS`/`BOARD_NOTE` (a `--status` without `--note` drops the source's
note); `--github public|private` also runs `gh repo create` and pushes;
`--no-git`, `--no-verify` and `--no-process-check` are for scripts and tests.
`~/Documents/repos/new-pedal.sh` predates this and copies from a location that
no longer exists; use `clone` instead.

`silk-labels` tidies reference designators after placement. For every 2-pad SMD
R/C/D/L footprint on the front, it puts the label north of a horizontal part
(horizontal text) or west of a vertical one (text reading bottom to top), with
the text centre 0.7 mm beyond the courtyard (`--gap`), the spacing KiCad's own
libraries use. ICs, LEDs, pots, switches and electrolytic cans are left alone.

- A label already on the right side (centred, 0.1-1.0 mm out) is kept, so
  hand-tuned gaps survive.
- A move that would land on a pad, inside another part's courtyard, on another
  label or off the board is not made; the run lists those parts and why.
- `--skip R12,C3` leaves named parts alone.
- With kicad-cli available, the planned board is DRC'd against the original on
  temp copies. Any move that adds a silkscreen violation is put back, and the
  run prints the silk counts before and after. `--no-drc` skips this check.

Only the `(at ...)` of each moved Reference field changes, so `git diff` shows
one line per moved label. The command refuses while the board is open in KiCad.
`--force` lets it run while KiCad is open on a different project.

`outline` checks each board outline (Edge.Cuts) at the nanometre level. KiCad's
DRC joins outline ends that lie within its own chaining tolerance, so a 10 µm
gap or a 20 µm stub left by stretching or filleting an edge passes DRC and then
breaks stricter tools (the kicad-live tidy planner, fab CAM). KiCad's Cleanup
Graphics does not reliably catch these.

It reads every board-level Edge.Cuts `gr_line`, `gr_arc`, `gr_rect`,
`gr_circle`, `gr_poly` and `gr_curve`. Edge.Cuts drawn inside footprints are
read as fixed context and never edited. The check (the default, read-only,
exit 1 on findings) reports:

- **stubs:** lines or arcs shorter than the tolerance (`--tol`, default
  0.05 mm);
- **gaps:** pairs of ends closer than the tolerance but not identical to the
  nanometre;
- **collinear splits:** lines that meet end to end on one straight line;
- **fold-backs:** a line that doubles back over its neighbour;
- **open ends:** ends with no partner within the tolerance, a really open
  outline;
- **closure:** whether the outline closes exactly, at zero tolerance, into one
  board polygon plus cutouts that neither cross nor touch. Several board
  outlines, for example a template holding a rectangle per enclosure size, are
  reported, but they do not block `--fix` and `check` does not count them.

`--fix` heals the board and `--dry-run` prints the same edits as a diff:

- Stubs are dropped.
- Each gap is snapped onto one exact point. A line end moves onto an arc,
  curve or footprint end, never the reverse, because moving an arc end changes
  its radius and centre. Between two lines, the end whose differing coordinate
  sits on the coarser grid stays.
- Collinear lines that meet end to end are merged into one.
- A stub between two arcs is kept, since nothing could close the gap without it.

Only the moved `(start ...)`/`(end ...)` tokens change, and dropped shapes are
removed whole, from any group too. The healed text is parsed again and must
chain exactly into clean loops before anything is written. Open ends and
fold-backs are reported, never guessed at; a fold-back's message names the
`--tol` that would heal it as a stub. Like `silk-labels`, `--fix` refuses while
the board is open in KiCad, and `--force` lets it run while KiCad has a
different project open.

`check` also runs the outline check, flagging boards with defects (everything
except collinear splits and several board outlines) and exiting 1 for them;
`--no-outline` skips it.
