"""Write the committee assembly: carrier + display. Binds stay JSON.

    python -m gat.demo.combined_usd_stage -o out/combined
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gat.adapters.openusd import openusd_available, write_openusd
from gat.adapters.openusd_compose import write_combined_stage
from gat.session import GatSession

MODEL = Path(__file__).with_name("model.ifc")
BIND = Path(__file__).resolve().parents[2] / "validation" / "cse-point-bind-v1.json"


def run_demo(output_directory: str) -> dict[str, str]:
    if not openusd_available():
        raise SystemExit("usd-core is not installed; pip install '.[openusd]'" )
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    session = GatSession.load_ifc(MODEL)
    carrier = output / "cse.usdc"
    write_openusd(session.world, carrier, ledger=session.ledger)
    combined = write_combined_stage(
        carrier_path=carrier,
        assembly_path=output / "world.usda",
        display_path=output / "sitelook.usda",
        bind_path=BIND if BIND.is_file() else None,
    )
    print(f"carrier {combined.carrier_path}")
    print(f"assembly {combined.assembly_path}")
    print(f"display {combined.display_path}")
    print("restart with GatSession.load_openusd on the carrier, not world.usda")
    print("binds remain JSON")
    return {
        "carrier": str(combined.carrier_path),
        "assembly": str(combined.assembly_path),
        "display": str(combined.display_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose CSE carrier + SiteLook display.")
    parser.add_argument("-o", "--output", default="out/combined")
    args = parser.parse_args()
    run_demo(args.output)


if __name__ == "__main__":
    main()
