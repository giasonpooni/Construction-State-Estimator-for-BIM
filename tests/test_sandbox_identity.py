"""Look surfaces must share EntityId and the cited pin digest."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from gat.harness.identity import (
    assert_look_surfaces_aligned,
    identity_from_disposition,
    workbench_has_entity,
)
from gat.harness.usd_projection import project_canonical_state
from gat.session import GatSession
from gat.workbench import state_payload


ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "validation" / "beam-b1-disposition-v1.json"
BEAM = ROOT / "gat" / "demo" / "beam_model.ifc"


class SandboxIdentityTests(unittest.TestCase):
    def test_pin_entity_is_in_workbench_and_projection(self) -> None:
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        session = GatSession.load_ifc(str(BEAM))
        state = state_payload(session.world)
        projection = project_canonical_state(
            disposition=pin,
            project_space_id="sandbox-beam-b1",
        ).document
        ident = identity_from_disposition(pin, project_space_id="sandbox-beam-b1")
        self.assertEqual(ident["entity"]["entity_id"], "IfcBeam:GATBEAMELEMENT00000100")
        self.assertTrue(
            workbench_has_entity(state, "IfcBeam", "GATBEAMELEMENT00000100")
        )
        self.assertEqual(
            projection["canonical_world_digest"],
            pin["revised_after_certificate"]["world_digest"],
        )
        self.assertEqual(
            projection["identity"]["entity"]["global_id"],
            "GATBEAMELEMENT00000100",
        )
        assert_look_surfaces_aligned(
            disposition=pin,
            projection=projection,
            workbench_state=state,
            project_space_id="sandbox-beam-b1",
        )
        self.assertNotEqual(
            state["world_digest"],
            pin["revised_after_certificate"]["world_digest"],
            msg="fresh IFC load is not the certificate checkpoint; do not hide that",
        )


if __name__ == "__main__":
    unittest.main()
