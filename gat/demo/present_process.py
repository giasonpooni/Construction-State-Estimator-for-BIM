"""Run the present-space process and write a packet. Never stamps.

    python -m gat.demo.present_process --demo -o out/present-packet
    python -m gat.demo.present_process --demo --lab --value 0.9 -o out/present-packet-lab
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.adapters.ifcopenshell_adapter import inventory_identities_cse
from gat.demo.present_space import (
    _DEMO_BIND,
    _DEMO_CAL,
    _DEMO_IFC,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    present_space,
)
from gat.session import GatSession

PROCESS = "cse-present-process-v1"
STAMP = {
    "kind": "refused",
    "record": None,
    "reason": "CSE does not issue ApprovalRecord or occupancy. An inspector stamps.",
}


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_process(
    *,
    output_dir: str | Path,
    model_path: str | Path = _DEMO_IFC,
    space_path: str | Path = _DEMO_SPACE,
    receipt_path: str | Path = _DEMO_RECEIPT,
    bind_path: str | Path | None = None,
    calibration_path: str | Path | None = None,
    lab: bool = False,
    value: float | None = None,
) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    session = GatSession.load_ifc(str(model_path))
    verification = session.verify()
    passed, warned, failed = verification.counts()
    _write(
        output / "01-verify.json",
        {
            "step": 1,
            "name": "verify",
            "passed": verification.passed,
            "counts": {"pass": passed, "warn": warned, "fail": failed},
            "world_digest": session.world.digest(),
        },
    )
    inventory = inventory_identities_cse(model_path)
    _write(
        output / "02-inventory.json",
        {
            "step": 2,
            "name": "inventory",
            "schema": inventory.schema,
            "product_count": inventory.product_count,
            "space_global_ids": list(inventory.space_global_ids),
            "opening_global_ids": list(inventory.opening_global_ids),
            "geometry_authority": inventory.geometry_authority,
        },
    )
    package = present_space(
        model_path=model_path,
        space_path=space_path,
        receipt_path=receipt_path,
        bind_path=bind_path if bind_path or not lab else _DEMO_BIND,
        calibration_path=calibration_path if calibration_path or not lab else _DEMO_CAL,
        apply_lab_observation=lab,
        observed_value=value if lab else None,
        output_path=output / "03-package.json",
    )
    package = {**package, "stamp": STAMP}
    _write(output / "03-package.json", package)
    _write(
        output / "04-stamp-refused.json",
        {
            "step": 4,
            "name": "stamp",
            **STAMP,
            "inspectability": package["inspectability"],
            "may_authorize": False,
        },
    )
    manifest = {
        "format": PROCESS,
        "steps": ["01-verify", "02-inventory", "03-package", "04-stamp-refused"],
        "inspectability": package["inspectability"],
        "verification_passed": package["verification"]["passed"],
        "may_authorize": False,
        "stamp": STAMP,
        "open_requests": package["open_requests"],
    }
    _write(output / "00-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Present-space process packet. Never stamps."
    )
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--lab", action="store_true", help="use shipped bind+calibration and observe")
    parser.add_argument("--value", type=float, default=0.9)
    parser.add_argument("-o", "--output", default="out/present-packet")
    args = parser.parse_args()
    manifest = run_process(
        output_dir=args.output,
        lab=args.lab,
        value=args.value if args.lab else None,
    )
    print(f"wrote {args.output}")
    print(f"inspectability {manifest['inspectability']}")
    print("stamp refused")


if __name__ == "__main__":
    main()
