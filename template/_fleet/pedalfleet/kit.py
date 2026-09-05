"""Load the fleet kit directory into one immutable object."""
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import KIT_DIR
from .rules import BEGIN_RE, END_RE


@dataclass(frozen=True)
class Kit:
    version: int
    fragment: dict          # merged into .kicad_pro
    rules_block: str        # begin marker … end marker, trailing newline
    gitignore: str


def load_kit(kit_dir: Path = KIT_DIR) -> Kit:
    rules_path = kit_dir / "fleet.kicad_dru"
    text = rules_path.read_text(encoding="utf-8")
    begin = BEGIN_RE.search(text)
    end = END_RE.search(text)
    if begin is None or end is None or end.start() < begin.start():
        raise ValueError(f"{rules_path}: fleet markers missing or out of order")
    block = text[begin.start():end.end()].rstrip("\n") + "\n"
    fragment = json.loads((kit_dir / "design_settings.json").read_text(encoding="utf-8"))
    gitignore = (kit_dir / "gitignore").read_text(encoding="utf-8")
    return Kit(version=int(begin.group(1)), fragment=fragment, rules_block=block, gitignore=gitignore)
