"""Write the look-only USD projection overlay from pinned sandbox artifacts.

    python -m gat.demo.usd_projection --demo -o out/usd-projection.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gat.harness.bundle import assemble_bundle, bind_commitment_file, load_json
from gat.harness.usd_projection import project_canonical_state
from gat.demo.experiment_harness import _DEMO_COMMITS, _DEFAULT_DISPOSITION


def run_usd_projection(
    *,
    disposition_path: str | Path | None,
    commitment_paths: list[str | Path],
    output_path: str | Path,
    project_space_id: str | None = None,
    quiet: bool = False,
) -> dict[str, object]:
    disposition = load_json(disposition_path) if disposition_path else None
    commitments = [
        (bind_commitment_file(path), str(path)) for path in commitment_paths
    ]
    bundle = assemble_bundle(
        commitments=commitments,
        disposition=disposition,
        project_space_id=project_space_id,
    )
    projection = project_canonical_state(
        disposition=disposition,
        bundle=bundle.document,
        project_space_id=project_space_id,
    )
    written = projection.write(output_path)
    if not quiet:
        layers = projection.document["layers"]
        print(f"wrote {written}")
        print(f"projection digest {projection.digest}")
        print(f"space {projection.document['project_space_id']}")
        print(
            "verdict "
            f"{layers['estimate']['prior_verdict']} -> "
            f"{layers['estimate']['revised_verdict']}"
        )
        print("mutates_source false; L_simulation empty; no usd-core required")
    return projection.document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project canonical GAT state to a look-only overlay. Does not prove."
    )
    parser.add_argument("--disposition")
    parser.add_argument("--commit", action="append", default=[])
    parser.add_argument("--project-space-id")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("-o", "--output", default="out/usd-projection.json")
    args = parser.parse_args()
    disposition = args.disposition
    commits = list(args.commit)
    space = args.project_space_id
    if args.demo:
        if disposition is None:
            disposition = str(_DEFAULT_DISPOSITION)
        commits.extend(str(path) for path in _DEMO_COMMITS)
        if space is None:
            space = "sandbox-beam-b1"
    run_usd_projection(
        disposition_path=disposition,
        commitment_paths=commits,
        output_path=args.output,
        project_space_id=space,
    )


if __name__ == "__main__":
    main()
