"""One command for the v0 packet. Does not stamp. Does not prove.

    python -m gat.demo.complete_v0 -o out/complete-v0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gat.harness.atlas import identity_gap, office_a_atlas
from gat.harness.atlas_fill import opening_component_atlas
from gat.harness.graph_views import functional_ledger, opening_factorization, spectral_atlas
from gat.harness.zkvm_numerics import admit_numeric_profile
from gat.harness.zkvm_scope import admit_guest
from gat.satellites.kernel_cost import cost_report
from gat.session import GatSession

_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parents[1]


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="out/complete-v0")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    office = GatSession.load_ifc(str(_DEMO / "model.ifc")).world.digest()
    beam_live = GatSession.load_ifc(str(_DEMO / "beam_model.ifc")).world.digest()
    pin = json.loads((_ROOT / "validation" / "beam-b1-disposition-v1.json").read_text())
    rci = json.loads((_DEMO / "harness_fixtures" / "p204-opening-rci.jsonl").read_text().splitlines()[0])
    full = spectral_atlas(office_a_atlas())
    component = spectral_atlas(opening_component_atlas(rci))
    gap = identity_gap(
        office_live_digest=office,
        beam_live_digest=beam_live,
        beam_prior_digest=pin["prior"]["world_digest"],
        beam_revised_digest=pin["revised_after_certificate"]["world_digest"],
    )
    cost = cost_report(_ROOT)
    guest = dict(admit_guest("beam-b1-f2-1", claim_scope="computational-integrity-only"))
    numerics = dict(admit_numeric_profile({"arithmetic": "checked-integer", "guest_id": "beam-b1-f2-1"}))
    _write(out / "spectral-full.json", full)
    _write(out / "spectral-opening.json", component)
    _write(out / "identity-gap.json", gap)
    _write(out / "factor-declaration.json", opening_factorization())
    _write(out / "functional-ledger.json", functional_ledger([]))
    _write(out / "kernel-cost.json", cost)
    _write(out / "zkvm-guest.json", guest)
    _write(out / "zkvm-numerics.json", numerics)
    status = {
        "schema": "cse-complete-v0",
        "released": False,
        "claim_scope": "record-integrity-only",
        "office_live_world_digest": office,
        "beam_live_world_digest": beam_live,
        "forced_common_world": False,
        "opening_component_connected": component["connected"],
        "opening_lambda2": component["algebraic_connectivity"],
        "full_atlas_connected": full["connected"],
        "isolated_slots": full["isolated_slots"],
        "field_evidence": False,
        "ieee754_guest": False,
        "sp1_cycles": cost["beam_guest"]["cycles"],
        "sp1_invoked": False,
        "sum_product": False,
        "sheaf": False,
        "riscv_flashed": False,
        "checks": {
            "opening_component_lambda2_positive": component["algebraic_connectivity"] > 0,
            "worlds_not_merged": gap["forced_common_world"] is False,
            "guest_admitted": guest["admitted"] is True,
            "cycles_not_invented": cost["beam_guest"]["cycles"] is None,
        },
        "refusals": [
            "Packet is presentable. It is not occupancy.",
            "Prototype/declared calibration is not a traceable certificate.",
            "SP1 cycles stay null until cargo execute fills them.",
        ],
    }
    status["complete"] = all(status["checks"].values())
    _write(out / "STATUS.json", status)
    print(f"wrote {out}/STATUS.json complete={status['complete']}")


if __name__ == "__main__":
    main()
