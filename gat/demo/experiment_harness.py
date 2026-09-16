"""Bind independently produced tool records into one experiment bundle.

    python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json
    python -m gat.demo.experiment_harness --inspectability --demo -o out/inspectability.json

Does not run SP1. Does not condition Beam-B1 on a millimetre.
Does not treat a digest as a point-to-IfcGuid bind.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gat.harness.bundle import (
    assemble_bundle,
    bind_commitment_file,
    load_json,
)
from gat.harness.inspectability import fold_inspectability

_FIXTURE_DIR = Path(__file__).resolve().parent / "harness_fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DISPOSITION = _REPO_ROOT / "validation" / "beam-b1-disposition-v1.json"
_DEMO_COMMITS = (
    _FIXTURE_DIR / "rci-example-commitment-v1.json",
    _FIXTURE_DIR / "torus-example-commitment-v1.json",
)
_DEMO_SPACE = _FIXTURE_DIR / "space-l3-office-a.json"
_DEMO_RECEIPT = _FIXTURE_DIR / "opening-17-receipt.json"


def run_experiment_harness(
    *,
    disposition_path: str | Path | None,
    commitment_paths: list[str | Path],
    output_path: str | Path,
    sp1_status: str = "NOT_REQUESTED",
    quiet: bool = False,
) -> dict[str, object]:
    disposition = load_json(disposition_path) if disposition_path else None
    commitments = [
        (bind_commitment_file(path), str(path)) for path in commitment_paths
    ]
    bundle = assemble_bundle(
        commitments=commitments,
        disposition=disposition,
        sp1_status=sp1_status,
    )
    written = bundle.write(output_path)
    if not quiet:
        print(f"wrote {written}")
        print(f"bundle digest {bundle.digest}")
        print(f"bound records {len(commitments)}")
        print("SP1 not invoked; claim_scope=record-integrity-only")
        if disposition is not None:
            prior = disposition.get("prior")
            revised = disposition.get("revised_after_certificate")
            if isinstance(prior, dict) and isinstance(revised, dict):
                print(
                    f"disposition {prior.get('verdict')} -> {revised.get('verdict')} "
                    "(unchanged by bound records)"
                )
    return bundle.document


def run_inspectability(
    *,
    space_path: str | Path | None,
    receipt_paths: list[str | Path],
    commitment_paths: list[str | Path],
    bind_paths: list[str | Path],
    output_path: str | Path,
    quiet: bool = False,
) -> dict[str, object]:
    space = load_json(space_path) if space_path else None
    receipts = [(load_json(path), str(path)) for path in receipt_paths]
    commitments = [(load_json(path), str(path)) for path in commitment_paths]
    binds = [(load_json(path), str(path)) for path in bind_paths]
    index = fold_inspectability(
        space=space,
        receipts=receipts,
        commitments=commitments,
        binds=binds,
    )
    written = index.write(output_path)
    if not quiet:
        print(f"wrote {written}")
        print(f"inspectability {index.inspectability}")
        print(f"open requests {len(index.document['open_requests'])}")
        print("read-only fold; not an occupancy permit")
    return index.document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bind tool records into a harness bundle, or fold an inspectability index. Does not prove."
    )
    parser.add_argument(
        "--disposition",
        help="Pinned GAT disposition JSON (e.g. validation/beam-b1-disposition-v1.json)",
    )
    parser.add_argument(
        "--commit",
        action="append",
        default=[],
        help="RCI or torus commitment JSON. Repeatable.",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        default=[],
        help="On-disk case receipt JSON for --inspectability. Repeatable.",
    )
    parser.add_argument(
        "--bind",
        action="append",
        default=[],
        help="Point-to-IfcGuid bind JSON (schema cse-point-bind-v1). Repeatable.",
    )
    parser.add_argument(
        "--space",
        help="Project/building/space identity JSON for --inspectability.",
    )
    parser.add_argument(
        "--inspectability",
        action="store_true",
        help="Fold receipts into cse-inspectability-index-v1 instead of a bundle.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Bind shipped fixtures and the Beam-B1 pin, or fold the shipped space receipt.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path",
    )
    parser.add_argument(
        "--sp1-status",
        default="NOT_REQUESTED",
        choices=("NOT_REQUESTED", "BACKEND_REQUIRED", "UNAVAILABLE"),
    )
    args = parser.parse_args()
    if args.inspectability:
        space = args.space
        receipts = list(args.receipt)
        commits = list(args.commit)
        binds = list(args.bind)
        if args.demo:
            if space is None:
                space = str(_DEMO_SPACE)
            receipts.append(str(_DEMO_RECEIPT))
            commits.extend(str(path) for path in _DEMO_COMMITS)
        output = args.output or "out/inspectability.json"
        run_inspectability(
            space_path=space,
            receipt_paths=receipts,
            commitment_paths=commits,
            bind_paths=binds,
            output_path=output,
        )
        return
    disposition = args.disposition
    commits = list(args.commit)
    if args.demo:
        if disposition is None:
            disposition = str(_DEFAULT_DISPOSITION)
        commits.extend(str(path) for path in _DEMO_COMMITS)
    output = args.output or "out/harness-bundle.json"
    run_experiment_harness(
        disposition_path=disposition,
        commitment_paths=commits,
        output_path=output,
        sp1_status=args.sp1_status,
    )


if __name__ == "__main__":
    main()
