"""Run a synthetic, read-only BIM-to-path planning exchange with a companion.

The two plane paths are fixtures, not geometry extracted from the IFC and not
registered scanner trajectories. Planning never supplies as-built evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from gat import GatSession
from gat.adapters.surface_inspection import inspect_report, prepare_request, replay_report
from gat.workflows import (
    AcceptanceCase,
    DifferenceDecision,
    WorkflowKind,
    assess_difference,
    difference_check,
    evaluate_acceptance_case,
)


def run(output: Path) -> dict:
    """Write one new retained fixture study; never overwrite a prior directory."""
    try:
        from geodesic_testbed import Units, constant_curvature_trace
        from geodesic_testbed.inspection import canonical, decode, evaluate
    except ImportError as exc:
        raise RuntimeError(
            "Install the reviewed Curved Surface Runtime inspection extension"
        ) from exc

    session = GatSession.load_ifc(Path(__file__).with_name("model.ifc"))
    world_digest = session.world.digest()
    entity = session.var("Opening-1", "Width").entity
    mapping = {
        "kind": "synthetic-planning-fixture",
        "spatial_frame_id": "declared-ifc-fixture-frame",
        "ifc_class": entity.ifc_class,
        "global_id": entity.global_id,
        "registration_performed": False,
        "description": "Two declared plane traverses, not derived from IFC solids or a scan.",
    }
    records = {
        label: constant_curvature_trace(np.linspace(0, length, 21), 0)
        .as_transfer_record(units=Units("m", "radian"))
        .to_dict()
        for label, length in (("short", 2), ("long", 6))
    }
    request = prepare_request(
        session.world,
        entity,
        quantity="Width",
        spatial_frame_id=mapping["spatial_frame_id"],
        mapping_digest=hashlib.sha256(canonical(mapping)).hexdigest(),
        records=records,
        tolerance={"lateral_m": 0.001, "heading_rad": 0.001},
        limits={
            "cross_track_m": 0.004,
            "heading_rad": 0.003,
            "path_length_m": 8.0,
            "wronskian_drift": 1e-8,
        },
    )

    def decision():
        checks = tuple(
            difference_check(
                quantity.lower(),
                assess_difference(
                    session.world,
                    DifferenceDecision(
                        session.var("Opening-1", quantity),
                        session.var("Door-1", quantity),
                        minimum_margin=0.05,
                        confidence=0.95,
                    ),
                ),
            )
            for quantity in ("Width", "Height")
        )
        return evaluate_acceptance_case(
            AcceptanceCase(
                "inspection-planning-demo",
                WorkflowKind.OPENING_VERIFICATION,
                "Door-1 into Opening-1",
                checks,
            )
        )

    before = decision()
    report = decode(canonical(evaluate(request, records)))
    bound = inspect_report(session.world, request, report)
    replayed = replay_report(session.world, request, report)
    after = decision()
    if session.world.digest() != world_digest or after != before:
        raise AssertionError("Planning changed the world or acceptance disposition")
    summary = {
        "example_kind": "synthetic_not_field_evidence",
        "ranking": report["ranking"],
        "within_sampled_limits": {
            r["candidate_id"]: r["within_sampled_limits"] for r in report["results"]
        },
        "world_unchanged": True,
        "as_built_disposition": after.disposition.value,
        "numerical_replay": replayed["numerical_replay"],
        "cryptographic_verification": "not_performed",
        "may_authorize": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("mapping", mapping),
        ("request", request),
        ("records", records),
        ("report", report),
        ("binding", bound),
        ("replay", replayed),
        ("summary", summary),
    ):
        (output / (name + ".json")).write_bytes(canonical(value) + b"\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = run(args.output)
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
