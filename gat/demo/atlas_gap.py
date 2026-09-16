"""Write the atlas, the world cites, and a JSPT covariance walk.

    python -m gat.demo.atlas_gap -o out/atlas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.harness.atlas import (
    OPENING_WIDTH_M,
    OPENING_WIDTH_MM,
    bind_rci_observation,
    cite_disposition_worlds,
    identity_gap,
    office_a_atlas,
    push_variance,
)
from gat.session import GatSession


_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parents[1]
_OFFICE = _DEMO / "model.ifc"
_BEAM = _DEMO / "beam_model.ifc"
_PIN = _ROOT / "validation" / "beam-b1-disposition-v1.json"
_RCI = _DEMO / "harness_fixtures" / "p204-opening-rci.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas, world cites, covariance walk.")
    parser.add_argument("-o", "--output", default="out/atlas")
    args = parser.parse_args()
    office = GatSession.load_ifc(str(_OFFICE)).world.digest()
    beam_live = GatSession.load_ifc(str(_BEAM)).world.digest()
    pin = json.loads(_PIN.read_text(encoding="utf-8"))
    atlas = office_a_atlas()
    record = json.loads(_RCI.read_text(encoding="utf-8").splitlines()[0])
    bind_rci_observation(atlas, record, OPENING_WIDTH_M)
    gap = identity_gap(
        office_live_digest=office,
        beam_live_digest=beam_live,
        beam_prior_digest=pin["prior"]["world_digest"],
        beam_revised_digest=pin["revised_after_certificate"]["world_digest"],
    )
    cites = cite_disposition_worlds(pin, beam_live_digest=beam_live)
    sigma_m = float(record["sigma"])
    variance_m = sigma_m * sigma_m
    variance_mm = push_variance(1000.0, variance_m)
    walked = atlas.walk(OPENING_WIDTH_M, OPENING_WIDTH_MM, float(record["indicated"]))
    cov = {
        "schema": "cse-covariance-calibration-v1",
        "claim_scope": "record-integrity-only",
        "law": "P' = T P T^T via JSPT push_covariance",
        "observation_id": record["observation_id"],
        "slot": OPENING_WIDTH_M,
        "sigma_m": sigma_m,
        "variance_m2": variance_m,
        "T": 1000.0,
        "c": 0.0,
        "variance_mm2": variance_mm,
        "sigma_mm": variance_mm ** 0.5,
        "mean_mm": walked["value"],
        "fused": False,
        "note": "Chart calibrates the 1x1 variance. This is not a Kalman update.",
    }
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "atlas-v1.json").write_text(json.dumps(atlas.to_document(), indent=2) + "\n")
    (out / "identity-gap-v1.json").write_text(json.dumps(gap, indent=2) + "\n")
    (out / "disposition-world-cite-v1.json").write_text(json.dumps(cites, indent=2) + "\n")
    (out / "covariance-calibration-v1.json").write_text(json.dumps(cov, indent=2) + "\n")
    print(f"office live {office}")
    print(f"beam live   {beam_live}")
    print(f"worlds cited separately: {not cites['same_world']}")
    print(f"obs edge {record['observation_id']} sigma={sigma_m}")
    print(f"P {variance_m} m^2 -> {variance_mm} mm^2")


if __name__ == "__main__":
    main()
