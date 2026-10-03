"""Budget observations retain the point bind's actual entity identity."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import gat.demo
from gat.adapters.budget_cite import BudgetCiteError, observe_from_budget
from gat.harness.point_bind import bind_point
from gat.ids import EntityId, VarId
from gat.session import GatSession


class BudgetBindIdentityTests(unittest.TestCase):
    def setUp(self):
        self.session = GatSession.load_ifc(
            str(Path(gat.demo.__file__).parent / "model.ifc")
        )
        self.var = self.session.var("Opening-1", "Width")
        self.bind = json.loads(
            (Path(__file__).resolve().parents[1] / "validation" /
             "cse-point-bind-v1.json").read_text(encoding="utf-8")
        )
        self.budget = {
            "schema": "uncertainty-budget-v1", "measurand": "Width",
            "unit": "m", "u_c": 0.002, "traceability": "none_claimed",
            "components": [{"type": "B", "source": "declared-resolution"}],
            "correlations": [], "combination": "gum_lpu",
        }

    def observe(self, bind=None, var=None):
        return observe_from_budget(
            self.var if var is None else var, 1.002, self.budget,
            bind=self.bind if bind is None else bind, slot_unit="m",
        )

    def assert_refused_without_state_change(self, bind=None, var=None):
        before = self.session.world.digest()
        with self.assertRaises(BudgetCiteError):
            self.observe(bind, var)
        self.assertEqual(self.session.world.digest(), before)

    def test_validated_bind_identity_is_retained_in_the_observation_record(self):
        validated = bind_point(self.bind)
        self.bind = validated.to_document()
        transform, record = self.observe()
        self.assertEqual(record["observed"]["bind_digest"], validated.digest)
        self.assertEqual(record["observed"]["bind_global_id"], self.var.entity.global_id)
        self.assertEqual(record["observed"]["bind_ifc_class"], self.var.entity.ifc_class)
        self.session.run(transform)

    def test_same_quantity_on_another_entity_is_refused(self):
        other = VarId(EntityId(self.var.entity.ifc_class, "GATOPN0000000000000999"), "Width")
        self.assert_refused_without_state_change(var=other)

    def test_same_global_id_in_another_ifc_class_is_refused(self):
        other = VarId(EntityId("IfcWall", self.var.entity.global_id), "Width")
        self.assert_refused_without_state_change(var=other)

    def test_coherently_rehashed_bind_for_another_entity_is_refused(self):
        moved = copy.deepcopy(self.bind)
        moved["payload"]["global_id"] = "GATOPN0000000000000999"
        moved["global_id"] = moved["payload"]["global_id"]
        moved = bind_point(moved).to_document()
        self.assert_refused_without_state_change(bind=moved)

    def test_schema_only_or_untyped_payload_is_not_an_observation_bind(self):
        for malformed in ({"schema": "cse-point-bind-v1", "quantity": "Width"},
                          {"quantity": "Width", "point_id": "P-Opening-1"},
                          {"payload": self.bind["payload"]}):
            with self.subTest(bind=malformed):
                self.assert_refused_without_state_change(bind=malformed)

    def test_missing_frame_epoch_or_sigma_cannot_bypass_bind_validation(self):
        for field in ("frame_id", "epoch", "sigma", "sigma_reason"):
            malformed = copy.deepcopy(self.bind)
            del malformed["payload"][field]
            with self.subTest(field=field):
                self.assert_refused_without_state_change(bind=malformed)

    def test_changed_digest_bound_payload_and_authority_claim_are_refused(self):
        changed = bind_point(self.bind).to_document()
        changed["payload"]["epoch"] = "different-epoch"
        self.assert_refused_without_state_change(bind=changed)
        promoted = copy.deepcopy(self.bind)
        promoted["payload"]["authorized"] = True
        self.assert_refused_without_state_change(bind=promoted)

    def test_conflicting_header_and_payload_identity_is_refused(self):
        for field, wrong in (("point_id", "P-Wrong"),
                             ("global_id", "GATOPN0000000000000999"),
                             ("ifc_class", "IfcWall")):
            changed = copy.deepcopy(self.bind)
            changed[field] = wrong
            with self.subTest(field=field):
                self.assert_refused_without_state_change(bind=changed)


if __name__ == "__main__":
    unittest.main()
