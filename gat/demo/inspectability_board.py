"""Print the Office-A inspectability board. Satellite demo. Not a stamp."""

from __future__ import annotations

import tempfile
from pathlib import Path

from gat.demo.experiment_harness import (
    _DEMO_COMMITS,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    run_inspectability,
)
from gat.harness.inspectability import fold_inspectability, tickets_from_index
from gat.harness.bundle import load_json


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        output = Path(raw) / "index.json"
        document = run_inspectability(
            space_path=_DEMO_SPACE,
            receipt_paths=[_DEMO_RECEIPT],
            commitment_paths=list(_DEMO_COMMITS),
            bind_paths=[],
            output_path=output,
            quiet=True,
        )
    space = load_json(_DEMO_SPACE)
    receipt = load_json(_DEMO_RECEIPT)
    index = fold_inspectability(
        space=space,
        receipts=[(receipt, str(_DEMO_RECEIPT))],
        commitments=[(load_json(path), str(path)) for path in _DEMO_COMMITS],
    )
    print(f"{document.get('project_id')} / {document.get('building_id')} / {document.get('space_id')}")
    print(f"inspectability={document['inspectability']}")
    print("tickets:")
    for ticket in tickets_from_index(index):
        print(f"  [{ticket.code}] {ticket.instrument_class}: {ticket.asks_for}")
    print("non-claims:")
    for line in document["non_claims"]:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
