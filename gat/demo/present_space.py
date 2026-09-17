"""Present one space as a package. Requires calibration and verification.

    python -m gat.demo.present_space --demo -o out/present.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from gat.adapters.ifcopenshell_adapter import inventory_identities_cse
from gat.corpus import CorpusError, load_corpus
from gat.engine.transform import ObserveQuantity
from gat.errors import GatError
from gat.harness.bundle import load_json
from gat.harness.inspectability import BIND_SCHEMA, fold_inspectability
from gat.session import GatSession

_REPO = Path(__file__).resolve().parents[2]
_DEMO_IFC = Path(__file__).with_name("model.ifc")
_DEMO_SPACE = Path(__file__).parent / "harness_fixtures" / "space-l3-office-a.json"
_DEMO_RECEIPT = Path(__file__).parent / "harness_fixtures" / "opening-17-receipt.json"
_DEMO_BIND = _REPO / "validation" / "cse-point-bind-v1.json"
_DEMO_CAL = _REPO / "validation" / "cse-calibration-v1.json"
OFFICE_A = "GATSPC0000000000000300"
CALIBRATION_SCHEMA = "cse-calibration-v1"


def _digest(payload: dict[str, object]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_calibration(path: str | Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    document = load_json(path)
    if document.get("schema") != CALIBRATION_SCHEMA:
        raise ValueError("calibration schema must be cse-calibration-v1")
    sigma = document.get("sigma")
    if not isinstance(sigma, (int, float)) or not float(sigma) > 0.0:
        raise ValueError("calibration sigma must be a positive finite number")
    target = document.get("target")
    if not isinstance(target, dict) or not target.get("quantity"):
        raise ValueError("calibration target.quantity is required")
    return document


def _corpus_block(space_global_id: str | None) -> dict[str, object]:
    corpus = load_corpus()
    in_i = isinstance(space_global_id, str) and space_global_id in corpus.global_ids()
    needles = []
    for row in corpus.free_coordinates:
        ident = row.get("id")
        if isinstance(ident, str):
            needles.append(ident)
    extra = []
    if space_global_id and not in_i:
        extra.append(
            {
                "code": "corpus.identity",
                "asks_for": "space GlobalId listed in invariant-corpus-v1",
            }
        )
    return {
        "schema": corpus.document["schema"],
        "space_in_corpus": in_i,
        "needles": needles,
        "extra_requests": extra,
    }


def present_space(
    *,
    model_path: str | Path,
    space_path: str | Path,
    receipt_path: str | Path | None = None,
    bind_path: str | Path | None = None,
    calibration_path: str | Path | None = None,
    apply_lab_observation: bool = False,
    observed_value: float | None = None,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    model_path = Path(model_path)
    session = GatSession.load_ifc(str(model_path))
    report = session.verify()
    inventory = inventory_identities_cse(model_path)
    space = load_json(space_path)
    receipts = []
    if receipt_path is not None:
        receipts.append((load_json(receipt_path), str(receipt_path)))
    binds = []
    if bind_path is not None:
        binds.append((load_json(bind_path), str(bind_path)))
    calibration = load_calibration(calibration_path)
    extra = []
    if calibration is None:
        extra.append(
            {
                "code": "calibration.declared",
                "asks_for": "cse-calibration-v1 with a finite sigma on the target quantity",
            }
        )
    ref = space.get("space_ref") if isinstance(space.get("space_ref"), dict) else {}
    space_guid = ref.get("global_id") if isinstance(ref, dict) else None
    if not isinstance(space_guid, str):
        space_guid = None
    corpus_block = _corpus_block(space_guid)
    extra.extend(corpus_block["extra_requests"])
    if apply_lab_observation:
        if calibration is None:
            raise GatError("lab observation requires cse-calibration-v1")
        if observed_value is None:
            raise GatError("lab observation requires --value")
        try:
            load_corpus().needle("var.opening-width")
        except CorpusError as exc:
            raise GatError(f"lab observation is not a corpus needle: {exc}") from exc
        target = calibration["target"]
        name = str(target.get("name") or "Opening-1")
        quantity = str(target["quantity"])
        var = session.var(name, quantity)
        session.run(
            ObserveQuantity.single(var, float(observed_value), float(calibration["sigma"])),
            provenance={
                "calibration_id": calibration["calibration_id"],
                "lab_observation": True,
                "traceable": bool(calibration.get("traceable")),
                "corpus_needle": "var.opening-width",
            },
        )
        report = session.verify()
        evidence = {
            "case_id": "opening-17",
            "workflow": "OPENING_VERIFICATION",
            "disposition": "ACCEPT" if report.passed else "REQUEST_EVIDENCE",
            "evidence_digest": _digest(
                {
                    "calibration_id": calibration["calibration_id"],
                    "value": observed_value,
                    "sigma": calibration["sigma"],
                    "world": session.world.digest(),
                }
            ),
        }
        receipts = [(evidence, "lab-observation")]
    index = fold_inspectability(
        space=space,
        receipts=receipts,
        binds=binds,
        extra_requests=extra,
    )
    office = next(
        (row for row in inventory.products if row.global_id == OFFICE_A),
        None,
    )
    payload = {
        "format": "cse-present-space-v1",
        "space_id": space.get("space_id"),
        "space_ref": space.get("space_ref"),
        "inventory_office_a": office.global_id if office else None,
        "inspectability": index.inspectability,
        "open_requests": index.document["open_requests"],
        "verification": {
            "passed": report.passed,
            "counts": list(report.counts()),
        },
        "calibration": {
            "present": calibration is not None,
            "calibration_id": None if calibration is None else calibration.get("calibration_id"),
            "traceable": False if calibration is None else bool(calibration.get("traceable")),
            "sigma": None if calibration is None else calibration.get("sigma"),
        },
        "bind": {
            "present": any(row.get("schema") == BIND_SCHEMA for row, _ in binds),
        },
        "corpus": {
            "schema": corpus_block["schema"],
            "space_in_corpus": corpus_block["space_in_corpus"],
            "needles": corpus_block["needles"],
        },
        "lab_observation_applied": apply_lab_observation,
        "world_digest": session.world.digest(),
        "may_authorize": False,
        "non_claims": [
            "not an occupancy permit",
            "declared calibration is not SI-traceable",
            "lab observation is not field evidence",
            "inference does not invent corpus names",
        ],
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package one space. Requires calibration and verification."
    )
    parser.add_argument("--model", default=str(_DEMO_IFC))
    parser.add_argument("--space", default=str(_DEMO_SPACE))
    parser.add_argument("--receipt", default=str(_DEMO_RECEIPT))
    parser.add_argument("--bind")
    parser.add_argument("--calibration")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--apply-lab-observation", action="store_true")
    parser.add_argument("--value", type=float, help="Lab indicated width in metres")
    parser.add_argument("-o", "--output", default="out/present.json")
    args = parser.parse_args()
    bind = args.bind
    calibration = args.calibration
    if args.demo and bind is None and args.apply_lab_observation:
        bind = str(_DEMO_BIND)
    if args.demo and calibration is None and args.apply_lab_observation:
        calibration = str(_DEMO_CAL)
    document = present_space(
        model_path=args.model,
        space_path=args.space,
        receipt_path=args.receipt,
        bind_path=bind,
        calibration_path=calibration,
        apply_lab_observation=args.apply_lab_observation,
        observed_value=args.value,
        output_path=args.output,
    )
    print(f"wrote {args.output}")
    print(f"inspectability {document['inspectability']}")
    print(f"corpus {document['corpus']['space_in_corpus']}")
    print(f"verification passed {document['verification']['passed']}")
    print(f"may_authorize {document['may_authorize']}")
    holes = ", ".join(row["code"] for row in document["open_requests"]) or "none"
    print(f"open {holes}")


if __name__ == "__main__":
    main()
