"""Write the atlas, the world cites, and a JSPT covariance walk.

    python -m gat.demo.atlas_gap -o out/atlas
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.harness.atlas import OPENING_WIDTH_M, OPENING_WIDTH_MM, identity_gap, office_a_atlas
from gat.harness.atlas_cov import bind_rci_observation, cite_disposition_worlds, push_variance
from gat.session import GatSession

_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="out/atlas")
    args = parser.parse_args()
    office = GatSession.load_ifc(str(_DEMO / "model.ifc")).world.digest()
    beam_live = GatSession.load_ifc(str(_DEMO / "beam_model.ifc")).world.digest()
    pin = json.loads((_ROOT / "validation" / "beam-b1-disposition-v1.json").read_text())
    atlas = office_a_atlas()
    record = json.loads((_DEMO / "harness_fixtures" / "p204-opening-rci.jsonl").read_text().splitlines()[0])
    bind_rci_observation(atlas, record, OPENING_WIDTH_M)
    cites = cite_disposition_worlds(pin, beam_live_digest=beam_live)
    sigma_m = float(record["sigma"])
    variance_mm = push_variance(1000.0, sigma_m * sigma_m)
    walked = atlas.walk(OPENING_WIDTH_M, OPENING_WIDTH_MM, float(record["indicated"]))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "gap": identity_gap(
            office_live_digest=office,
            beam_live_digest=beam_live,
            beam_prior_digest=pin["prior"]["world_digest"],
            beam_revised_digest=pin["revised_after_certificate"]["world_digest"],
        ),
        "cites": cites,
        "covariance": {
            "schema": "cse-covariance-calibration-v1",
            "law": "P' = T P T^T via JSPT push_covariance",
            "observation_id": record["observation_id"],
            "sigma_m": sigma_m,
            "T": 1000.0,
            "variance_mm2": variance_mm,
            "sigma_mm": variance_mm ** 0.5,
            "mean_mm": walked["value"],
            "fused": False,
        },
    }
    (out / "atlas-v1.json").write_text(json.dumps(atlas.to_document(), indent=2) + "\n")
    (out / "identity-gap-v1.json").write_text(json.dumps(payload["gap"], indent=2) + "\n")
    (out / "disposition-world-cite-v1.json").write_text(json.dumps(cites, indent=2) + "\n")
    (out / "covariance-calibration-v1.json").write_text(json.dumps(payload["covariance"], indent=2) + "\n")
    print(f"worlds cited separately: {not cites['same_world']}")
    print(f"P {sigma_m*sigma_m} m^2 -> {variance_mm} mm^2")


if __name__ == "__main__":
    main()
