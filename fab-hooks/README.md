# fab-hooks

Pre/post generation hooks for
[kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools)
(generation-hook feature, PR #743). Every fab-output generation gets: a
FABLOG.md row, a git commit, an annotated tag `<board>-<rev>-g<count>`, and a
push to origin.

Setup and rollout instructions are at the bottom of this file (added in Task 8).
