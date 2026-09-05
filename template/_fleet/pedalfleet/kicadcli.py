"""Run kicad-cli DRC and make sense of its JSON report."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .paths import KICAD_CLI_DEFAULT

PROBE_NAME = "pedal-fleet probe: fires once per footprint when this file parses"
PROBE_RULE = (
    f'(rule "{PROBE_NAME}"\n'
    "  (condition \"A.Type == 'Footprint'\")\n"
    "  (constraint assertion \"A.Type != 'Footprint'\"))\n"
)
REF_RE = re.compile(r"\b([A-Z]{1,3})\d+[A-Z]?\b")
FOOTPRINT_RE = re.compile(r'^\s*\(footprint\s+"', re.M)


def find_kicad_cli(explicit=None) -> Path:
    for candidate in (explicit, os.environ.get("KICAD_CLI"), KICAD_CLI_DEFAULT, shutil.which("kicad-cli")):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise FileNotFoundError("kicad-cli not found: install KiCad, pass --kicad-cli, or set KICAD_CLI")


def run_drc(kicad_cli: Path, pcb: Path, out_json: Path) -> dict:
    command = [str(kicad_cli), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
               "-o", str(out_json), str(pcb)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not Path(out_json).exists():
        raise RuntimeError(f"kicad-cli drc failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(Path(out_json).read_text(encoding="utf-8"))


@dataclass
class DrcSummary:
    total: int = 0                 # non-excluded violations
    excluded: int = 0
    errors: int = 0                # non-excluded, severity error
    by_type: Counter = field(default_factory=Counter)
    severities: dict = field(default_factory=dict)
    prefixes: dict = field(default_factory=lambda: defaultdict(Counter))


def summarize(report: dict) -> DrcSummary:
    summary = DrcSummary()
    for violation in report.get("violations", []):
        if violation.get("excluded"):
            summary.excluded += 1
            continue
        kind = violation["type"]
        summary.total += 1
        summary.by_type[kind] += 1
        summary.severities[kind] = violation.get("severity", "")
        if violation.get("severity") == "error":
            summary.errors += 1
        for item in violation.get("items", []):
            match = REF_RE.search(item.get("description", ""))
            if match:
                summary.prefixes[kind][match.group(1) + "*"] += 1
    return summary


def involving(report: dict, types, ref_pattern: str) -> int:
    """Non-excluded violations of the given types with an item whose description matches ref_pattern."""
    pattern = re.compile(ref_pattern)
    count = 0
    for violation in report.get("violations", []):
        if violation.get("excluded") or violation["type"] not in types:
            continue
        if any(pattern.search(item.get("description", "")) for item in violation.get("items", [])):
            count += 1
    return count


def probe_fired(report: dict) -> int:
    return sum(1 for v in report.get("violations", [])
               if v["type"] == "assertion_failure" and PROBE_NAME in v.get("description", ""))


def count_footprints(board_text: str) -> int:
    return len(FOOTPRINT_RE.findall(board_text))


def delta(before: DrcSummary, after: DrcSummary) -> list:
    kinds = sorted(set(before.by_type) | set(after.by_type))
    return [(kind, before.by_type.get(kind, 0), after.by_type.get(kind, 0)) for kind in kinds]


def validate_rules(kicad_cli: Path, pro: Path) -> str:
    """'ok', 'broken' or 'no-footprints'.

    kicad-cli ignores an unparsable rules file silently (exit 0, no stderr), so the project is copied to a temp
    dir, a probe rule is appended, and DRC is run: the probe fails one assertion per footprint if, and only if,
    the whole file parses.
    """
    pro = Path(pro)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for suffix in (".kicad_pro", ".kicad_pcb", ".kicad_dru"):
            source = pro.with_suffix(suffix)
            if source.exists():
                shutil.copy2(source, work / source.name)
        pcb = work / pro.with_suffix(".kicad_pcb").name
        if count_footprints(pcb.read_text(encoding="utf-8")) == 0:
            return "no-footprints"
        rules = work / pro.with_suffix(".kicad_dru").name
        text = rules.read_text(encoding="utf-8") if rules.exists() else "(version 1)\n"
        rules.write_text(text.rstrip("\n") + "\n" + PROBE_RULE, encoding="utf-8")
        report = run_drc(kicad_cli, pcb, work / "probe.json")
        return "ok" if probe_fired(report) > 0 else "broken"
