#!/usr/bin/env python3
"""Migrate a sibling repo's invariant corpus from v1 to v2.

v2 requires a ``chart`` on every free coordinate: the coordinate system the
declaration in ``needs`` fixes the quantity in. See docs/invariant-corpus-v2.md
for the chart assigned to each member of the index.

    python3 validation/migrate_corpus_v2.py ../Parameterized-Lyapunov-Stability-Runtime chart.plsr-plant

Writes validation/invariant-corpus-v2.json next to the v1 file and leaves the
v1 file in place; removing it is the sibling repo's own commit. Refuses to
overwrite an existing v2 file, and refuses a chart already claimed by another
member in this repo's index.

stdlib only. Run it from the CSE checkout.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
INDEX = _ROOT / "validation" / "invariant-corpus-index-v2.json"
CHART_PREFIX = "chart."


def claimed_charts() -> dict[str, str]:
    """chart -> repo, from the canonical index."""
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    claimed: dict[str, str] = {}
    for row in index.get("members", []):
        for chart in (row.get("charts") or {}).values():
            claimed[chart] = row["repo"]
    return claimed


def migrate(document: dict, chart: str) -> dict:
    """Return the v2 document. Each free coordinate gains the chart after id."""
    out = collections.OrderedDict(document)
    out["schema"] = "invariant-corpus-v2"
    coordinates = []
    for row in document.get("free_coordinates", []):
        rebuilt = collections.OrderedDict()
        for key, value in row.items():
            rebuilt[key] = value
            if key == "id":
                rebuilt["chart"] = chart
        if "chart" not in rebuilt:  # a row with no id at all
            rebuilt["chart"] = chart
        coordinates.append(rebuilt)
    out["free_coordinates"] = coordinates
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    repo, chart = Path(argv[0]).expanduser().resolve(), argv[1]

    if not chart.startswith(CHART_PREFIX):
        print(f"chart must start with {CHART_PREFIX!r}", file=sys.stderr)
        return 2

    claimed = claimed_charts()
    owner = claimed.get(chart)
    if owner is None:
        print(
            f"{chart!r} is not in {INDEX.name}. Add the member there first so "
            "charts stay globally unique.",
            file=sys.stderr,
        )
        return 2
    if owner.lower() not in repo.name.lower().replace("_", "-"):
        print(
            f"{chart!r} is claimed by {owner}, which is not {repo.name}. "
            "Charts are globally unique; pick this member's own chart.",
            file=sys.stderr,
        )
        return 2

    source = repo / "validation" / "invariant-corpus-v1.json"
    target = repo / "validation" / "invariant-corpus-v2.json"
    if not source.is_file():
        print(f"no {source}", file=sys.stderr)
        return 2
    if target.exists():
        print(f"{target} already exists; not overwriting", file=sys.stderr)
        return 2

    document = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=collections.OrderedDict)
    if document.get("schema") != "invariant-corpus-v1":
        print(f"{source} is {document.get('schema')!r}, not invariant-corpus-v1", file=sys.stderr)
        return 2

    migrated = migrate(document, chart)
    target.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
    needles = [row.get("id") for row in migrated["free_coordinates"]]
    print(f"wrote {target}")
    print(f"  schema : invariant-corpus-v2")
    print(f"  chart  : {chart}")
    print(f"  needles: {needles}")
    print(f"\n{source.name} is left in place; removing it is {repo.name}'s own commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
