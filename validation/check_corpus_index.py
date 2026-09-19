#!/usr/bin/env python3
"""Check the corpus index against the sibling corpora it claims.

validation/invariant-corpus-index-v2.json names twelve members, each with the
needles it declares and the chart those needles live in. Nothing verified that
any of it was true: a member could be listed without a corpus, declare a
different needle, or claim a chart another member already owns.

Point this at a directory holding sibling clones (or pass paths explicitly) and
it reports, per member, whether the claim holds:

    python3 validation/check_corpus_index.py ~/src
    python3 validation/check_corpus_index.py ~/src/PLSR ~/src/JSPT

Members with no clone present are reported as unchecked, not as failures --
companion clones stay separate by design, so a partial checkout is normal. Exit
status is non-zero only when a claim is contradicted.

stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
INDEX = _ROOT / "validation" / "invariant-corpus-index-v2.json"
CANONICAL_CITE = "giasonpooni/Construction-State-Estimator-for-BIM"
CORPUS_NAMES = ("invariant-corpus-v2.json", "invariant-corpus-v1.json")


def load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def find_corpus(repo_dir: Path) -> Path | None:
    """The member's corpus, newest schema first."""
    for name in CORPUS_NAMES:
        candidate = repo_dir / "validation" / name
        if candidate.is_file():
            return candidate
    return None


def locate(member: str, roots: list[Path]) -> Path | None:
    """A clone of ``member`` among ``roots``, matched case-insensitively."""
    wanted = member.lower().replace("_", "-")
    for root in roots:
        if not root.is_dir():
            continue
        if root.name.lower().replace("_", "-") == wanted and find_corpus(root):
            return root
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if child.name.lower().replace("_", "-") == wanted and find_corpus(child):
                return child
    return None


def check_member(row: dict, repo_dir: Path) -> list[str]:
    """Problems with one member's corpus. Empty means the claim holds."""
    problems: list[str] = []
    path = find_corpus(repo_dir)
    if path is None:
        return [f"no validation/{CORPUS_NAMES[0]} (or v1) under {repo_dir}"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path.name} is unreadable: {error}"]

    schema = document.get("schema")
    if schema not in ("invariant-corpus-v2", "invariant-corpus-v1"):
        problems.append(f"schema {schema!r} is not an invariant corpus")
    if document.get("claim_scope") != "computational-integrity-only":
        problems.append(f"claim_scope is {document.get('claim_scope')!r}")
    if row["role"] != "canonical" and document.get("cites") != CANONICAL_CITE:
        problems.append(f"cites {document.get('cites')!r}, not the canonical repo")

    declared = {
        coordinate.get("id"): coordinate.get("chart")
        for coordinate in document.get("free_coordinates", [])
        if isinstance(coordinate, dict)
    }
    for needle in row["needles"]:
        if needle not in declared:
            problems.append(f"index claims {needle!r}; corpus declares {sorted(declared)}")
            continue
        claimed = row["charts"][needle]
        actual = declared[needle]
        if actual is None:
            if schema == "invariant-corpus-v2":
                problems.append(f"{needle} declares no chart in a v2 corpus")
            # v1 carries no chart at all: not a contradiction, just unmigrated.
        elif actual != claimed:
            problems.append(
                f"{needle} is in {actual!r}; the index claims {claimed!r}"
            )
    return problems


def check_index(index: dict) -> list[str]:
    """Problems inside the index itself, before any clone is consulted."""
    problems: list[str] = []
    owner: dict[str, str] = {}
    for row in index["members"]:
        charts = row.get("charts") or {}
        for needle in row["needles"]:
            if needle not in charts:
                problems.append(f"{row['repo']}: {needle} has no chart")
                continue
            chart = charts[needle]
            if chart in owner:
                problems.append(
                    f"chart {chart} is claimed by {owner[chart]} and {row['repo']}"
                )
            owner[chart] = row["repo"]
    canonical = [r for r in index["members"] if r["role"] == "canonical"]
    if len(canonical) != 1:
        problems.append(f"expected exactly one canonical member, found {len(canonical)}")
    return problems


def main(argv: list[str]) -> int:
    roots = [Path(a).expanduser().resolve() for a in argv] or [_ROOT.parent]
    index = load_index()

    internal = check_index(index)
    if internal:
        print("index is internally inconsistent:")
        for problem in internal:
            print(f"  {problem}")
        return 1

    print(f"index: {len(index['members'])} members, searching {len(roots)} root(s)")
    checked = failed = unchecked = 0
    for row in sorted(index["members"], key=lambda r: r["repo"]):
        member = row["repo"]
        if member.lower() in CANONICAL_CITE.lower():
            repo_dir: Path | None = _ROOT
        else:
            repo_dir = locate(member, roots)
        if repo_dir is None:
            print(f"  ---- {member}: no clone found")
            unchecked += 1
            continue
        problems = check_member(row, repo_dir)
        if problems:
            failed += 1
            print(f"  FAIL {member}")
            for problem in problems:
                print(f"         {problem}")
        else:
            checked += 1
            charts = ", ".join(sorted(row["charts"].values()))
            print(f"  ok   {member}  [{charts}]")

    print(f"\n{checked} verified, {failed} contradicted, {unchecked} not present")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
