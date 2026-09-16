"""Bind independently produced tool records into one experiment bundle.

    python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json

Does not run SP1. Does not condition Beam-B1 on a millimetre.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gat.harness.bundle import (
    assemble_bundle,
    bind_commitment_file,
    load_json,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "harness_fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DISPOSITION = _REPO_ROOT / "validation" / "beam-b1-disposition-v1.json"
_DEMO_COMMITS = (
    _FIXTURE_DIR / "rci-example-commitment-v1.json",
    _FIXTURE_DIR / "torus-example-commitment-v1.json",
)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bind tool records into a harness bundle. Does not prove."
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
        "--demo",
        action="store_true",
        help="Bind shipped fixtures and the Beam-B1 pin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="out/harness-bundle.json",
        help="Bundle path",
    )
    parser.add_argument(
        "--sp1-status",
        default="NOT_REQUESTED",
        choices=("NOT_REQUESTED", "BACKEND_REQUIRED", "UNAVAILABLE"),
    )
    args = parser.parse_args()
    disposition = args.disposition
    commits = list(args.commit)
    if args.demo:
        if disposition is None:
            disposition = str(_DEFAULT_DISPOSITION)
        commits.extend(str(path) for path in _DEMO_COMMITS)
    run_experiment_harness(
        disposition_path=disposition,
        commitment_paths=commits,
        output_path=args.output,
        sp1_status=args.sp1_status,
    )


if __name__ == "__main__":
    main()
