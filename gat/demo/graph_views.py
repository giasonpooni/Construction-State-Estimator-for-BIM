"""Write the three graph views. Does not run inference.

    python -m gat.demo.graph_views -o out/graph-views
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.harness.atlas import office_a_atlas
from gat.harness.graph_views import functional_ledger, opening_factorization, spectral_atlas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="out/graph-views")
    args = parser.parse_args()
    atlas = office_a_atlas()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    spec = spectral_atlas(atlas)
    (out / "spectral-atlas-v1.json").write_text(json.dumps(spec, indent=2) + "\n")
    (out / "functional-ledger-v1.json").write_text(json.dumps(functional_ledger([]), indent=2) + "\n")
    (out / "factor-declaration-v1.json").write_text(json.dumps(opening_factorization(), indent=2) + "\n")
    print(f"atlas nodes {len(spec['nodes'])} lambda2 {spec['algebraic_connectivity']:.4g}")
    print("factor declaration sum-product", opening_factorization()["sum_product"])


if __name__ == "__main__":
    main()
