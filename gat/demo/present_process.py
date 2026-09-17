"""Run the present-space process and write a packet. Never stamps.

    python -m gat.demo.present_process --demo -o out/present-packet
    python -m gat.demo.present_process --demo --public-xref -o out/present-packet-xref
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.adapters.ifcopenshell_adapter import inventory_identities_cse
from gat.adapters.integrity_citation import kernel_citation, validate_citation
from gat.demo.present_space import (
    _DEMO_BIND,
    _DEMO_CAL,
    _DEMO_IFC,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    present_space,
)
from gat.harness.bundle import load_json
from gat.session import GatSession
from gat.sp1_kernel import host_callback

PROCESS = "cse-present-process-v1"
_REPO = Path(__file__).resolve().parents[2]
_PUBLIC_CAL = _REPO / "validation" / "cse-calibration-public-xref-v1.json"
_PUBLIC_OBS = _REPO / "validation" / "simulated-opening-width-observe-v1.json"
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
    public_xref: bool = False,
    value: float | None = None,
) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    observe = lab or public_xref
    if public_xref:
        bind_path = bind_path or _DEMO_BIND
        calibration_path = calibration_path or _PUBLIC_CAL
        if value is None:
            value = float(load_json(_PUBLIC_OBS)["indicated_m"])
    elif lab:
        bind_path = bind_path or _DEMO_BIND
        calibration_path = calibration_path or _DEMO_CAL
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
        bind_path=bind_path,
        calibration_path=calibration_path,
        apply_lab_observation=observe,
        observed_value=value if observe else None,
        output_path=output / "03-package.json",
    )
    package = {
        **package,
        "stamp": STAMP,
        "simulation": public_xref,
        "not_field_evidence": True if public_xref else package.get("lab_observation_applied"),
    }
    _write(output / "03-package.json", package)
    _write(
        output / "04-stamp-refused.json",
        {
            "step": 4,
            "name": "stamp",
            **STAMP,
            "inspectability": package["inspectability"],
            "may_authorize": False,
            "simulation": public_xref,
        },
    )
    if public_xref:
        _write(
            output / "05-public-xref.json",
            {
                "step": 5,
                "name": "public-xref",
                "calibration": load_json(_PUBLIC_CAL),
                "observation": load_json(_PUBLIC_OBS),
            },
        )
    kernel_receipt = host_callback(None)
    kernel_receipt.write(output / "kernel_sp1_receipt.json")
    citation = validate_citation(
        kernel_citation(locator="kernel_sp1_receipt.json", is_proof=kernel_receipt.is_proof)
    )
    _write(
        output / "06-integrity-citation.json",
        {
            "step": 6,
            "name": "integrity-citation",
            "note": "Pointer only. Proof bytes stay out of USD.",
            "citation": citation,
        },
    )
    steps = ["01-verify", "02-inventory", "03-package", "04-stamp-refused"]
    if public_xref:
        steps.append("05-public-xref")
    steps.append("06-integrity-citation")
    manifest = {
        "format": PROCESS,
        "steps": steps,
        "inspectability": package["inspectability"],
        "verification_passed": package["verification"]["passed"],
        "may_authorize": False,
        "stamp": STAMP,
        "simulation": public_xref,
        "open_requests": package["open_requests"],
        "citations": [citation],
    }
    _write(output / "00-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Present-space process packet. Never stamps."
    )
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--lab", action="store_true")
    parser.add_argument(
        "--public-xref",
        action="store_true",
        help="simulate observation from public instrument specs + demo QTO",
    )
    parser.add_argument("--value", type=float)
    parser.add_argument("-o", "--output", default="out/present-packet")
    args = parser.parse_args()
    if args.lab and args.value is None:
        args.value = 0.9
    manifest = run_process(
        output_dir=args.output,
        lab=args.lab,
        public_xref=args.public_xref,
        value=args.value,
    )
    print(f"wrote {args.output}")
    print(f"inspectability {manifest['inspectability']}")
    print("stamp refused")
    print(f"citation {manifest['citations'][0]['statement_digest'][:16]}... not a proof")


if __name__ == "__main__":
    main()
