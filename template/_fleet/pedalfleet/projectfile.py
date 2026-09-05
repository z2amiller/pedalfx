"""Read, patch and compare KiCad .kicad_pro files (JSON) without disturbing anything else."""
import copy
import json
from pathlib import Path

PRUNABLE_EXCLUSIONS = ("silk_edge_clearance", "silk_over_copper", "silk_overlap", "courtyards_overlap")
EMPTY_CLASS_SETTINGS = {"assignments": [], "meta": {"version": 0}, "sheet_component_classes": {"enabled": False}}


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dumps(pro: dict) -> str:
    """KiCad writes two-space-indented JSON with a trailing newline; this reproduces it byte for byte."""
    return json.dumps(pro, indent=2, ensure_ascii=False) + "\n"


def save(path: Path, pro: dict) -> None:
    Path(path).write_text(dumps(pro), encoding="utf-8")


def _assignment_key(assignment: dict) -> str:
    return json.dumps({"c": assignment.get("component_class"), "k": assignment.get("conditions")}, sort_keys=True)


def deep_merge(dst: dict, src: dict) -> bool:
    """Merge src into dst in place: dicts recurse, everything else overwrites. Returns True if dst changed."""
    changed = False
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            changed = deep_merge(dst[key], value) or changed
        elif key not in dst or dst[key] != value:
            dst[key] = copy.deepcopy(value)
            changed = True
    return changed


def merge_assignments(existing: list, kit_assignments: list) -> bool:
    """Insert or update kit assignments by (class, conditions) identity; keep every other entry."""
    by_key = {_assignment_key(a): a for a in existing}
    changed = False
    for wanted in kit_assignments:
        key = _assignment_key(wanted)
        current = by_key.get(key)
        if current is None:
            existing.append(copy.deepcopy(wanted))
            changed = True
        elif current != wanted:
            current.clear()
            current.update(copy.deepcopy(wanted))
            changed = True
    return changed


def merge_fragment(pro: dict, fragment: dict) -> bool:
    frag = copy.deepcopy(fragment)
    kit_assignments = frag.get("component_class_settings", {}).pop("assignments", None)
    changed = deep_merge(pro, frag)
    if kit_assignments is not None:
        ccs = pro.setdefault("component_class_settings", {})
        for key, value in EMPTY_CLASS_SETTINGS.items():
            if key not in ccs:
                ccs[key] = copy.deepcopy(value)
                changed = True
        changed = merge_assignments(ccs["assignments"], kit_assignments) or changed
    return changed


def drift(pro: dict, fragment: dict) -> list:
    """Human-readable differences between a project and the kit fragment. Empty list means in sync."""
    problems = []
    frag = copy.deepcopy(fragment)
    kit_assignments = frag.get("component_class_settings", {}).pop("assignments", [])

    def walk(have: dict, want: dict, path: str):
        for key, value in want.items():
            here = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                if not isinstance(have.get(key), dict):
                    problems.append(f"{here}: missing")
                else:
                    walk(have[key], value, here)
            elif key not in have:
                problems.append(f"{here}: missing (kit {value!r})")
            elif have[key] != value:
                problems.append(f"{here}: {have[key]!r} != kit {value!r}")

    walk(pro, frag, "")
    present = {_assignment_key(a) for a in pro.get("component_class_settings", {}).get("assignments", [])}
    for wanted in kit_assignments:
        if _assignment_key(wanted) not in present:
            problems.append(f"component class {wanted['component_class']} {json.dumps(wanted['conditions'])}: missing")
    return problems


def exclusion_type(entry) -> str:
    text = entry[0] if isinstance(entry, list) else entry
    return str(text).split("|", 1)[0]


def _exclusions(pro: dict) -> list:
    return pro.get("board", {}).get("design_settings", {}).get("drc_exclusions") or []


def count_exclusions(pro: dict, types=PRUNABLE_EXCLUSIONS) -> int:
    return sum(1 for e in _exclusions(pro) if exclusion_type(e) in types)


def prune_exclusions(pro: dict, types=PRUNABLE_EXCLUSIONS) -> int:
    """Drop exclusions of the given types. Returns how many were removed."""
    current = _exclusions(pro)
    if not current:
        return 0
    kept = [e for e in current if exclusion_type(e) not in types]
    pro["board"]["design_settings"]["drc_exclusions"] = kept
    return len(current) - len(kept)
