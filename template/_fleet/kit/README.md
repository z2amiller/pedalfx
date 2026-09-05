# Fleet kit

Everything in this directory is stamped into every template and board by
`pedal-fleet apply`. Edit here, never in a template.

| file                   | goes to                                                                                 | what it does                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fleet.kicad_dru`      | `<project>.kicad_dru`, between the `# --- pedalfx fleet rules vN begin/end ---` markers | pot and jack silkscreen may cross the board edge, mask, copper and other silk; pot pads may sit 0.2 mm apart; jack courtyards may overlap each other; reference and value fields must be at least 0.8 mm high and 0.15 mm thick on silk; pot text at 0.75 mm is tolerated; `Tall` parts are disallowed inside a `BACKPACK_KEEPOUT` rule area                                                    |
| `design_settings.json` | `<project>.kicad_pro`                                                                   | silk defaults 0.8 × 0.8 × 0.15 mm with 0.15 mm lines, fab 0.8 × 0.8 × 0.15 mm, "apply board defaults to footprint fields" on (so placed footprints' references and values take these sizes; footprint text and freeform text keep their own), component classes `Pot` (RV\*), `Jack` (J\*), `Switch` (SW\*), `Tall` (pot, switch, Neutrik, 3PDT, radial electrolytic and pin-socket footprints) |
| `gitignore`            | `.gitignore` in every template (boards only when they have none)                        | KiCad's ignore set; KiCad also honours it when instantiating a template, so backups and caches never copy                                                                                                                                                                                                                                                                                       |

Rules written by hand in a board's `.kicad_dru` **outside** the markers are kept
and, because later rules win, override the fleet block.

## Checklist: a new template type

1. In KiCad, create a project from the closest existing template and build the
   board content: outline on Edge.Cuts, enclosure marks on User.2–User.4, named
   rule areas (`BACKPACK_KEEPOUT`, `PUMP_KEEPOUT`, …), the power sub-sheet.
1. Set the title-block revision to the sentinel `X.Y` so derived boards must set
   a real one before the fab hooks pass.
1. Save and quit KiCad (pedal-fleet refuses to touch a project KiCad has open).
1. `cd ~/Documents/repos/pedalfx/template/_fleet && uv run pedal-fleet new-template <Name> --from <project dir> --title "…" --description "…"`
1. `uv run pedal-fleet drc --templates --fail-on error` — must be clean.
1. `git add template/<Name> && git commit`.
1. In KiCad, File → New Project from Template → pick it → confirm the new
   project has `<new>.kicad_dru`, Board Setup → Text & Graphics shows
   0.8/0.8/0.15 with "apply defaults to footprint fields" ticked, and Component
   Classes lists Pot, Jack, Switch, Tall.
