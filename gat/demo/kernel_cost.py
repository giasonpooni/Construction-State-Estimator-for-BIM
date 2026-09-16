"""Write the i32 kernel cost pin.\n\n    python -m gat.demo.kernel_cost -o out/kernel-cost\n"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.satellites.kernel_cost import cost_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="out/kernel-cost")
    args = parser.parse_args()
    document = cost_report(Path(__file__).resolve().parents[2])
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "kernel-cost-v1.json"
    path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"wrote {path}")
    print(f"beam binary present {document['beam_guest']['binary_present']}")
    for row in document["kernels"]:
        print(f"{row['name']} muls={row['i32_muls']} adds={row['i32_adds']}")


if __name__ == "__main__":
    main()
