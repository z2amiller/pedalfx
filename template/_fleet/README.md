# pedal-fleet

Keeps every KiCad template in `pedalfx/template/` and every board under
`~/Documents/repos` on the shared fleet kit in [`kit/`](kit/README.md): DRC
rules, text defaults and component classes.

```
cd ~/Documents/repos/pedalfx/template/_fleet
uv run pedal-fleet check --all              # read-only drift report, exit 1 on drift
uv run pedal-fleet apply --templates        # stamp the kit into the templates
uv run pedal-fleet apply --boards --commit  # retrofit the fleet, one commit per repo, no push
uv run pedal-fleet apply fx-Foo --dry-run   # show the diff for one project
uv run pedal-fleet drc --templates --fail-on error
uv run pedal-fleet drc fx-Foo --save before.json   # later: --baseline before.json
uv run pedal-fleet new-template Name --from ~/Documents/repos/fx-Foo --title "..." --description "..."
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
