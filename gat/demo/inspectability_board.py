"""Print the Office-A inspectability board. Satellite demo. Not a stamp."""

from __future__ import annotations

import json
import os

from gat.inspectability.index import record_from_document, tickets_from_index


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    pin = os.path.join(root, "validation", "inspectability-space-l3-office-a-v1.json")
    with open(pin, encoding="utf-8") as handle:
        document = json.load(handle)
    record = record_from_document(document)
    print(f"{record.project_id} / {record.building_id} / {record.space_id}")
    print(f"inspectability={record.inspectability}")
    print("tickets:")
    for ticket in tickets_from_index(record):
        print(f"  [{ticket.code}] {ticket.instrument_class}: {ticket.asks_for}")
    print("non-claims:")
    for line in record.non_claims:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
