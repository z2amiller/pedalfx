# fab-hooks

Pre/post generation hooks for
[kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools)
(generation-hook feature, PR #743). Every fab-output generation gets: a
FABLOG.md row, a git commit, an annotated tag `<board>-<rev>-g<count>`, and a
push to origin.

The revision on the board stays human-managed (`${REVISION}` silk resolved from
the board's title block); the hooks only record, tag, and push — they never bump
versions for you.

## How it works

- `pre_generate.py` (advisory): fails the pre-hook (the plugin then shows a
  Continue/Cancel dialog) if the project isn't a git repo, has no `origin`
  remote, or the board's revision — read from the title block, falling back to a
  matching text on silk — isn't valid. Revisions are `[prefix]N.M`: an optional
  letter/dash prefix plus major.minor, so `v0.1`, `0.3`, and `psu-1.0` are all
  fine. An unreachable origin (offline) is only a warning.
- `post_generate.py`: appends `| date | board | rev | gen | zip-sha12 | | |` to
  `FABLOG.md` at the repo root, copies the gerber zip to the repo root when the
  GitHub repo behind `origin` is **public** (see below), commits the project
  directory plus those files (pathspec-scoped, so unrelated staged work is never
  swept in), creates annotated tag `fx-BloodySMD-v0.1-g17`, and pushes HEAD plus
  the tag atomically. Local-first: a failed push never loses the commit or tag.
  Refuses to overwrite existing tags, and validates the tag name before touching
  anything.
- `set_board_rev.py board.kicad_pcb v0.1`: one-time rollout helper to set the
  title-block rev (close KiCad first — it aborts if KiCad's lock file is
  present).

## Gerbers at the repo root (public repos)

People who don't run KiCad can order a board from a public repo's README if the
gerber zip sits at the root. The post-hook does that copy itself:
`GERBER-<board>.zip` (the plugin's own name, so a README link stays valid across
revisions) lands at the repo root in the same commit and tag as the generation,
and the FABLOG row's hash identifies it. Visibility comes from
`gh repo view --json visibility` run in the repo (`gh` is found via
`$FABHOOKS_GH`, PATH, then the Homebrew locations, because KiCad launches hooks
with the GUI's minimal PATH). Private repos get nothing at the root. If `gh` is
missing, offline, or `origin` isn't on GitHub, the hook says "visibility
unknown" and skips the copy rather than guessing.
`FABHOOKS_REPO_VISIBILITY=public|private` overrides the lookup (tests, or
forcing a private repo to publish).

## Plugin configuration (one-time, global)

Hook settings are global plugin settings (stored in the plugin's
`settings.json`, edited via the kicad-jlcpcb-tools **Settings** dialog):

- Pre-generate hook script: `<checkout>/fab-hooks/pre_generate.py`
- Post-generate hook script: `<checkout>/fab-hooks/post_generate.py`
- Hook timeout: `60` seconds (covers the push)

## Per-board rollout checklist

1. Repo: if the project isn't a git repo yet, initialize it and add an `origin`
   remote (the pre-hook reminds you).
1. Close KiCad, then: `./set_board_rev.py <board>.kicad_pcb v0.1` (use the rev
   that matches already-fabbed reality).
1. In KiCad: replace any literal version silk text with `${REVISION}` so the
   title block is the single source of truth.
1. Generate through the plugin; check `FABLOG.md` and `git tag` afterwards.

## Version discipline

- Bump the rev (title block, via KiCad or `set_board_rev.py`) whenever the
  design meaningfully changes. The hooks never bump it for you.
- Forgot to bump? The FABLOG still disambiguates: same rev, different gen counts
  and zip hashes.

## Ordering tips (JLCPCB)

- JLCPCB's order flow can print a serial number / 2D barcode on the board. The
  prefix field takes up to 34 characters — paste the git tag the hooks just
  created (e.g. `fx-BloodySMD-v0.1-g17`) and every physical board comes back
  marked with the exact tag plus a per-unit serial. Optional but free
  traceability.
- Record any JLC-printed code in the FABLOG's "JLC Order #" column when boards
  arrive to link physical batches back to rows.

## Testing

`python3 -m pytest tests/ -v` — fully offline (temp repos with a local bare
origin; hermetic git config).

Manual dry-run against a real project:

```
JLCPCB_BOARD_PATH=.../fx-Example.kicad_pcb \
JLCPCB_PROJECT_DIR=.../fx-Example \
JLCPCB_GENERATION_COUNT=999 \
JLCPCB_ARTIFACT_GERBER_ZIP=.../jlcpcb/production_files/GERBER-fx-Example.zip \
./post_generate.py --dry-run
```
