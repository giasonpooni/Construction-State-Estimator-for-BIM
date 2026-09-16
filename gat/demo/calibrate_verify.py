"""Calibrate a named slot, observe it, verify the world. Refuse gaps.

    python -m gat.demo.calibrate_verify --demo -o out/calibrate-verify

Requires a calibration declaration and a measurement. Writes a verification
report. Prototype calibrations cannot be field evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.engine.executor import execute
from gat.engine.verify import run_invariants
from gat.evidence import CalibratedObservation, EvidenceKind
from gat.harness.calibration import (
    load_calibration_file,
    load_measurement_file,
    bind_measurement,
)
from gat.harness.inspectability import fold_inspectability
from gat.harness.point_bind import assert_bind_in_world, bind_point_file
from gat.ledger import write_ledger
from gat.session import GatSession


_DEMO = Path(__file__).resolve().parent
_MODEL = _DEMO / "model.ifc"
_BIND = _DEMO / "harness_fixtures" / "p204-opening-bind.json"
_SPACE = _DEMO / "harness_fixtures" / "space-office-a-model.json"
_CAL = _DEMO / "harness_fixtures" / "p204-opening-calibration-v1.json"
_MEAS = _DEMO / "harness_fixtures" / "p204-opening-measurement-v1.json"


def _entity(session: GatSession, ifc_class: str, global_id: str):
    for entity in session.world.module.entities.values():
        if entity.id.ifc_class == ifc_class and entity.id.global_id == global_id:
            return entity
    raise KeyError(f"{ifc_class}:{global_id}")


def _mean(session: GatSession, name: str, quantity: str) -> float:
    for entity in session.world.module.entities.values():
        if entity.name == name and quantity in entity.slots:
            return float(session.world.full.mean(entity.var(quantity)))
    raise KeyError(f"{name}.{quantity}")


def run_calibrate_verify(
    *,
    model_path: str | Path,
    calibration_path: str | Path,
    measurement_path: str | Path,
    bind_path: str | Path | None,
    space_path: str | Path | None,
    output_dir: str | Path,
    margin: float = 0.05,
) -> dict[str, object]:
    calibration = load_calibration_file(calibration_path)
    measurement = load_measurement_file(measurement_path)
    indicated_si = bind_measurement(calibration, measurement)
    session = GatSession.load_ifc(str(model_path))
    bind_doc = None
    if bind_path is not None:
        bind = bind_point_file(bind_path)
        assert_bind_in_world(bind, session.world)
        bind_doc = bind.to_document()
        if bind.global_id != calibration.global_id:
            raise ValueError("bind GlobalId does not match calibration subject")
    entity = _entity(session, calibration.ifc_class, calibration.global_id)
    subject = entity.var(calibration.quantity)
    slot_unit = session.world.module.entities[subject.entity].slots[subject.quantity].unit.value
    if calibration.canonical_unit != slot_unit:
        raise ValueError("calibration canonical_unit does not match IR unit")
    source = Path(calibration_path).read_bytes() + Path(measurement_path).read_bytes()
    observation = CalibratedObservation.from_source_bytes(
        measurement.observation_id,
        subject,
        EvidenceKind.MEASURED,
        indicated_si,
        measurement.sigma,
        calibration.canonical_unit,
        source,
        calibration.calibration_id,
        calibration.digest,
    )
    prior = session.world
    result = execute(prior, observation.transformation(prior))
    if not result.committed:
        raise RuntimeError("observation was not committed")
    event = session.ledger.record_transition(
        prior,
        result,
        provenance=observation.provenance(),
    )
    session.world = result.world
    report = run_invariants(session.world)
    opening = _mean(session, "Opening-1", "Width")
    door = _mean(session, "Door-1", "Width")
    fit_margin = opening - door
    fit_ok = fit_margin >= margin
    field_ok = (not calibration.not_traceable) and report.passed and fit_ok
    if calibration.not_traceable:
        verification_disposition = "REQUEST_EVIDENCE"
        reason = "calibration is prototype / not_traceable"
    elif not report.passed:
        verification_disposition = "REJECT"
        reason = "invariant verification failed"
    elif not fit_ok:
        verification_disposition = "REQUEST_EVIDENCE"
        reason = f"opening-door margin {fit_margin:.6g} < {margin}"
    else:
        verification_disposition = "ACCEPT"
        reason = "invariants passed and fit margin met under declared calibration"
    receipt = {
        "case_id": "opening-17-calibrate-verify",
        "workflow": "OPENING_VERIFICATION",
        "disposition": verification_disposition,
        "subject": f"{calibration.ifc_class}:{calibration.global_id}.{calibration.quantity}",
        "evidence_digest": observation.digest(),
        "evidence_kind": "calibrated-quantity",
        "prior_world_digest": prior.digest(),
        "result_world_digest": session.world.digest(),
        "ledger_event_hash": event.event_hash,
        "calibration_id": calibration.calibration_id,
        "calibration_digest": calibration.digest,
        "not_traceable": calibration.not_traceable,
        "usable_as_field_evidence": field_ok,
    }
    space = json.loads(Path(space_path).read_text(encoding="utf-8")) if space_path else None
    index = fold_inspectability(
        space=space,
        receipts=[(receipt, "calibrate-verify-receipt")],
        binds=[(bind_doc, str(bind_path))] if bind_doc is not None else (),
    )
    document = {
        "schema": "cse-calibrate-verify-report-v1",
        "claim_scope": "record-integrity-only",
        "released": False,
        "calibration": calibration.to_document(),
        "measurement": {
            "observation_id": measurement.observation_id,
            "indicated": measurement.indicated,
            "applied": indicated_si,
            "sigma": measurement.sigma,
            "digest": measurement.digest,
        },
        "verification": {
            "passed": report.passed,
            "counts": list(report.counts()),
            "disposition": verification_disposition,
            "reason": reason,
            "opening_width_m": opening,
            "door_width_m": door,
            "fit_margin_m": fit_margin,
            "required_margin_m": margin,
            "failures": [
                {
                    "id": item.invariant_id,
                    "subject": item.subject,
                    "detail": item.detail,
                }
                for item in report.failures
            ],
        },
        "receipt": receipt,
        "inspectability": index.inspectability,
        "world_digest": session.world.digest(),
        "refusals": [
            "Prototype calibration is not a traceable certificate.",
            "Verification is not an occupancy permit.",
            "A passing invariant is not field evidence when not_traceable is true.",
        ],
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibrate-verify-report.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    )
    (out / "inspectability.json").write_text(
        json.dumps(index.document, indent=2, sort_keys=True) + "\n"
    )
    write_ledger(session.ledger, out / "ledger.json")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Observe a slot only after calibration, then verify. Does not stamp."
    )
    parser.add_argument("--model")
    parser.add_argument("--calibration")
    parser.add_argument("--measurement")
    parser.add_argument("--bind")
    parser.add_argument("--space")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("-o", "--output", default="out/calibrate-verify")
    parser.add_argument("--margin", type=float, default=0.05)
    args = parser.parse_args()
    model = args.model
    calibration = args.calibration
    measurement = args.measurement
    bind = args.bind
    space = args.space
    if args.demo:
        model = model or str(_MODEL)
        calibration = calibration or str(_CAL)
        measurement = measurement or str(_MEAS)
        bind = bind or str(_BIND)
        space = space or str(_SPACE)
    missing = [
        name
        for name, value in (
            ("--model", model),
            ("--calibration", calibration),
            ("--measurement", measurement),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"required: {', '.join(missing)}")
    document = run_calibrate_verify(
        model_path=model,
        calibration_path=calibration,
        measurement_path=measurement,
        bind_path=bind,
        space_path=space,
        output_dir=args.output,
        margin=args.margin,
    )
    print(f"wrote {args.output}/calibrate-verify-report.json")
    print(
        f"calibration {document['calibration']['status']} "
        f"digest {document['calibration']['digest']}"
    )
    print(
        f"verification {document['verification']['disposition']}: "
        f"{document['verification']['reason']}"
    )
    print(f"inspectability {document['inspectability']}")
    print(f"field evidence {document['receipt']['usable_as_field_evidence']}")


if __name__ == "__main__":
    main()
