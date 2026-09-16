"""V0 Office-A cut: bind P-204, observe opening width, fold inspectability.

Satellite demo. Does not import lyapunov. Does not call a camera.
Does not treat inspectability ACCEPT as a stamp.
"""

from __future__ import annotations

import json
from pathlib import Path

from gat.engine.executor import execute
from gat.evidence import CalibratedObservation, EvidenceKind
from gat.harness.inspectability import fold_inspectability, tickets_from_index
from gat.harness.point_bind import assert_bind_in_world, bind_point_file
from gat.session import GatSession


_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parents[1]
_MODEL = _DEMO / "model.ifc"
_BIND = _DEMO / "harness_fixtures" / "p204-opening-bind.json"
_SPACE = _DEMO / "harness_fixtures" / "space-office-a-model.json"
_RECEIPT = _DEMO / "harness_fixtures" / "opening-17-as-built-receipt.json"
_LAYOUT_NOTE = _DEMO / "harness_fixtures" / "p204-layout-note.txt"


def _entity_by_name(session: GatSession, name: str):
    for entity in session.world.module.entities.values():
        if entity.name == name:
            return entity
    raise KeyError(name)


def observe_opening_width(session: GatSession):
    opening = _entity_by_name(session, "Opening-1")
    subject = opening.var("Width")
    source = _LAYOUT_NOTE.read_bytes()
    observation = CalibratedObservation.from_source_bytes(
        "obs:opening-1-width-p204",
        subject,
        EvidenceKind.MEASURED,
        1.002,
        0.005,
        "m",
        source,
        "layout-point-p204-declared-width",
    )
    prior = session.world
    result = execute(prior, observation.transformation(prior))
    if not result.committed:
        raise RuntimeError("opening width observation was not committed")
    event = session.ledger.record_transition(
        prior,
        result,
        provenance=observation.provenance(),
    )
    session.world = result.world
    return observation, event


def write_as_built_receipt(observation, event, prior_digest: str, result_digest: str):
    document = {
        "case_id": "opening-17",
        "workflow": "OPENING_VERIFICATION",
        "disposition": "ACCEPT",
        "subject": "Door-1 into Opening-1",
        "evidence_digest": observation.digest(),
        "evidence_kind": "calibrated-quantity",
        "prior_world_digest": prior_digest,
        "result_world_digest": result_digest,
        "ledger_event_hash": event.event_hash,
        "calibration_id": "layout-point-p204-declared-width",
    }
    _RECEIPT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def main() -> None:
    if not _LAYOUT_NOTE.exists():
        _LAYOUT_NOTE.write_text(
            "P-204 layout note: Opening-1 width declared 1.002 m from point P-204.\n",
            encoding="utf-8",
        )
    session = GatSession.load_ifc(str(_MODEL))
    bind = bind_point_file(_BIND)
    assert_bind_in_world(bind, session.world)
    sealed = bind.to_document()
    _BIND.write_text(json.dumps(sealed, indent=2) + "\n", encoding="utf-8")

    prior_digest = session.world.digest()
    observation, event = observe_opening_width(session)
    receipt = write_as_built_receipt(
        observation, event, prior_digest, session.world.digest()
    )

    space = json.loads(_SPACE.read_text(encoding="utf-8"))
    index = fold_inspectability(
        space=space,
        receipts=[(receipt, "gat/demo/harness_fixtures/opening-17-as-built-receipt.json")],
        binds=[(sealed, "gat/demo/harness_fixtures/p204-opening-bind.json")],
    )
    out = _ROOT / "validation" / "office-a-v0-inspectability.json"
    index.write(out)
    print(f"space {index.document.get('space_id')}")
    print(f"inspectability {index.inspectability}")
    print(f"bind digest {bind.digest}")
    print(f"evidence digest {receipt['evidence_digest']}")
    print(f"wrote {out}")
    tickets = tickets_from_index(index)
    if tickets:
        print("tickets:")
        for ticket in tickets:
            print(f"  [{ticket.code}] {ticket.instrument_class}: {ticket.asks_for}")
    else:
        print("tickets: none (presentable, not a stamp)")


if __name__ == "__main__":
    main()
