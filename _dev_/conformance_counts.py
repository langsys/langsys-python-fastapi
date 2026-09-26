#!/usr/bin/env python3
"""Count CONFORMANCE.md against the spec's rule ids, in the fleet's canonical format.

    python3 _dev_/conformance_counts.py [path/to/sdk-spec.mdx]

Adapted from langsys-python's counter of the same name, for the canonical layout: two
header rows, then one status table headed ``| Rule | Status | Tier | Evidence |`` with one
rule id per row. With no argument the spec is read from git at the pinned commit, and
counting is refused if that commit's blob is not the pinned one — so the tally is always
against the revision the file says it is filed against.

The exit code is about accounting integrity only: a rule id missing, unknown or graded
twice; a status or tier outside the vocabulary; a status its tier cannot carry; a header row
missing. GREEN (no row partial, not implemented or held) is reported, not enforced, and
`provisional` rows are counted separately.
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
#: Overridable so the counter itself can be checked against synthetic files.
CONFORMANCE = Path(os.environ.get("CONFORMANCE_FILE") or REPO_ROOT / "CONFORMANCE.md")
LANGSYS2 = Path.home() / "Documents" / "dev" / "langsys2"

#: Pinned by commit, not by branch: a branch moves, and this must resolve the revision the
#: rows were actually filed against.
SPEC_COMMIT = "a95af2c2596d5a882473d9ef09d232eb5c1d7a12"
SPEC_BLOB = "5d7e6890b733a50fb6f5f5c30e0056c6ef7bcf45"
SPEC_PATH = "docs/sdk-spec.mdx"

RULE_HEADING = re.compile(r"^### ([A-Z]+-\d+) ", re.M)
RULE_ID = re.compile(r"^[A-Z]+-\d+$")
TABLE_HEADER = "| Rule | Status | Tier | Evidence |"
STATUS = re.compile(
    r"^(implemented|provisional|delegated|partial|not implemented|held \(strip ruling\)|waived"
    r"|n/a \(profile: [^)]+\)|n/a \(architecture: .+\))$"
)
TIERS = {"live", "contract", "mock", "n/a (pure)", "-"}
#: Which tiers a status can carry. `implemented` needs evidence that counts (CONF-2),
#: `provisional` is exactly the mock-only case, a `delegated` row's tier lives on the core's
#: row, and an `n/a` row has nothing to grade.
ALLOWED = {
    "implemented": {"live", "contract", "n/a (pure)"},
    "provisional": {"mock"},
    "delegated": {"-"},
    "n/a": {"-"},
}
NOT_GREEN = ("partial", "not implemented", "held")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(LANGSYS2), *args], capture_output=True, text=True, check=True
    ).stdout


def spec_text(argv: list[str]) -> str:
    if len(argv) > 1:
        return Path(argv[1]).read_text(encoding="utf-8")
    blob = _git("rev-parse", f"{SPEC_COMMIT}:{SPEC_PATH}").strip()
    if blob != SPEC_BLOB:
        raise SystemExit(
            f"ERROR - {SPEC_COMMIT[:12]}:{SPEC_PATH} resolves to {blob}, pinned {SPEC_BLOB}"
        )
    return _git("show", f"{SPEC_COMMIT}:{SPEC_PATH}")


def cells(line: str) -> list[str]:
    parts = UNESCAPED_PIPE.split(line.strip().strip("|"))
    return [p.strip().replace("**", "").strip("`").strip() for p in parts]


def main(argv: list[str]) -> int:
    rules = RULE_HEADING.findall(spec_text(argv))
    lines = CONFORMANCE.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []

    header = {}
    for line in lines:
        if match := re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|(.*)\|\s*$", line):
            header.setdefault(match.group(1), match.group(2))
    if SPEC_BLOB not in header.get("Spec revision read", ""):
        problems.append("header: `Spec revision read` does not cite the pinned blob")
    if not header.get("Profiles", "").strip():
        problems.append("header: no `Profiles` row")

    starts = [i for i, line in enumerate(lines) if line.startswith(TABLE_HEADER)]
    if len(starts) != 1:
        raise SystemExit(f"ERROR - expected exactly one status table, found {len(starts)}")

    graded: collections.Counter[str] = collections.Counter()
    tally: collections.Counter[str] = collections.Counter()
    for line in lines[starts[0] + 2 :]:
        if not line.startswith("|"):
            break
        row = cells(line)
        if len(row) < 4 or not RULE_ID.match(row[0]):
            problems.append(f"row {row[0]!r}: one rule id per row")
            continue
        rule, status, tier = row[0], row[1], row[2]
        graded[rule] += 1
        if not STATUS.match(status):
            problems.append(f"{rule}: status {status!r} is not in the vocabulary")
        if tier not in TIERS:
            problems.append(f"{rule}: tier {tier!r} is not in the vocabulary")
        family = "n/a" if status.startswith("n/a") else status
        if family in ALLOWED and tier not in ALLOWED[family]:
            problems.append(f"{rule}: `{status}` cannot carry tier {tier!r}")
        if status.startswith("n/a (profile"):
            tally["n/a (profile)"] += 1
        elif status.startswith("n/a"):
            tally["n/a (architecture)"] += 1
        elif status == "implemented":
            tally[f"implemented ({tier})"] += 1
        else:
            tally[status] += 1

    missing = [r for r in rules if r not in graded]
    extra = sorted(set(graded) - set(rules))
    twice = sorted(r for r, n in graded.items() if n > 1)

    source = argv[1] if len(argv) > 1 else f"commit {SPEC_COMMIT[:12]}, blob {SPEC_BLOB[:12]}"
    print(f"spec rules: {len(rules)}  ({source})")
    for name, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {name:30} {n}")
    print(f"  {'TOTAL':30} {sum(tally.values())}")

    for label, items in (
        ("unaccounted for", missing),
        ("not in the spec", extra),
        ("graded more than once", twice),
    ):
        if items:
            problems.append(f"{label}: {items}")

    blocking = {k: v for k, v in tally.items() if k.startswith(NOT_GREEN)}
    print(f"\nGREEN: {'yes' if not problems and not blocking else 'no'}")
    for name, n in sorted(blocking.items()):
        print(f"  blocked by: {name} x{n}")
    if tally.get("provisional"):
        print(f"  provisional (counted separately): {tally['provisional']}")
    for problem in problems:
        print(f"ERROR - {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
