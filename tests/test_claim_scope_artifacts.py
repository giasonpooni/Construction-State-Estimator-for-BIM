"""The artifacts that hold the demotions, checked against the code.

Four validation artifacts state the claims this project is careful about --
public code minima are not IFC widths, a zkVM guest attests arithmetic and not
evidence, SP1 is refused and uninvoked. All four were read by nothing, so the
demotions they record could drift from the code that is supposed to enforce
them, silently and in either direction.

Two of them duplicate a policy the code also holds as a frozenset. That
duplication is the point: the artifact is the published claim and the frozenset
is the enforcement, and a test that they agree is the only thing making the
published claim true.

stdlib unittest only.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from gat.harness.effort import decide_satellite, load_effort_table
from gat.harness.zkvm_numerics import ADMITTED, REFUSED, admit_numeric_profile
from gat.harness.zkvm_scope import ALLOWED, FORBIDDEN, admit_guest
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
VALIDATION = _ROOT / "validation"
MODEL = _ROOT / "gat" / "demo" / "model.ifc"


def _load(name: str) -> dict:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


class PublicCrossrefTests(unittest.TestCase):
    """Code minima cited next to a design width, and kept distinct from it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = _load("public-crossref-opening-v1.json")
        cls.session = GatSession.load_ifc(str(MODEL))

    def test_it_is_scoped_and_disclaims_field_evidence(self) -> None:
        self.assertEqual(self.doc["claim_scope"], "record-integrity-only")
        self.assertIs(self.doc["not_field_evidence"], True)

    def test_the_subject_exists_in_the_model(self) -> None:
        subject = self.doc["subject"]
        entity = next(
            e
            for e in self.session.world.module.entities.values()
            if e.global_id == subject["global_id"]
        )
        self.assertEqual(entity.id.ifc_class, subject["ifc_class"])
        self.assertEqual(entity.name, subject["name"])

    def test_the_quoted_priors_are_the_model_s_own(self) -> None:
        # The drift guard: edit the demo model and this artifact goes stale.
        prior = self.doc["ifc_prior"]
        module = self.session.world.module
        opening = module.slot(self.session.var("Opening-1", "Width"))
        door = module.slot(self.session.var("Door-1", "Width"))
        self.assertEqual(prior["opening_width_m"], opening.prior_mu)
        self.assertEqual(prior["opening_sigma_m"], opening.prior_sigma)
        self.assertEqual(prior["door_width_m"], door.prior_mu)
        self.assertEqual(prior["door_sigma_m"], door.prior_sigma)

    def test_every_minimum_says_it_is_not_the_ifc_width(self) -> None:
        # Entries come in two shapes: a floor carries value_m and the refusal,
        # a manufacturing tolerance carries a plus/minus band and no floor.
        floors = [f for f in self.doc["public_floors"] if "value_m" in f]
        bands = [f for f in self.doc["public_floors"] if "value_m" not in f]
        self.assertTrue(floors)
        self.assertTrue(bands)
        for floor in floors:
            self.assertIs(
                floor["same_as_ifc_width"], False, f"{floor['id']} lost its refusal"
            )
            self.assertTrue(floor["citation"])
        for band in bands:
            self.assertIn("plus_m", band)
            self.assertIn("minus_m", band)
            self.assertNotIn("same_as_ifc_width", band)

    def test_the_three_refusals_are_present_verbatim(self) -> None:
        refusals = self.doc["refusals"]
        self.assertIn("Clear width is not IfcOpeningElement.Width.", refusals)
        self.assertIn("A code minimum is not a measurement of P-204.", refusals)
        self.assertIn("SDI tolerance is not a total-station sigma.", refusals)

    def test_the_sdi_coincidence_is_refused_not_hidden(self) -> None:
        # simulation sigma equals the SDI-117 linear tolerance exactly, which is
        # the number most likely to be misread as an instrument sigma. The
        # artifact must keep using it AND keep refusing that reading.
        sdi = next(f for f in self.doc["public_floors"] if f["id"] == "sdi-117-linear")
        self.assertEqual(self.doc["simulation"]["sigma_sdi117_m"], sdi["value_m"])
        self.assertIn("SDI tolerance is not a total-station sigma.", self.doc["refusals"])

    def test_the_simulation_is_labelled_a_simulation(self) -> None:
        simulation = self.doc["simulation"]
        self.assertIn("indicated_m", simulation)
        self.assertIn("offset_from_design_m", simulation)
        self.assertIs(self.doc["not_field_evidence"], True)


class ZkvmGuestScopeTests(unittest.TestCase):
    """The published guest list is the enforced guest list."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = _load("zkvm-guest-scope-v1.json")

    def test_the_published_allow_list_is_the_code_s(self) -> None:
        self.assertEqual({g["id"] for g in self.doc["allowed_guests"]}, set(ALLOWED))

    def test_the_published_deny_list_is_the_code_s(self) -> None:
        self.assertEqual(set(self.doc["forbidden_guests"]), set(FORBIDDEN))

    def test_it_claims_no_zero_knowledge(self) -> None:
        self.assertIs(self.doc["zero_knowledge"], False)
        self.assertEqual(self.doc["claim_scope"], "computational-integrity-only")

    def test_every_forbidden_guest_is_actually_refused(self) -> None:
        for guest in self.doc["forbidden_guests"]:
            with self.assertRaises(ValueError, msg=guest):
                admit_guest(guest, claim_scope="computational-integrity-only")

    def test_the_allowed_guest_is_admitted_and_agrees_on_the_kernel_claim(self) -> None:
        for guest in self.doc["allowed_guests"]:
            admitted = admit_guest(guest["id"], claim_scope=self.doc["claim_scope"])
            self.assertIs(admitted["admitted"], True)
            self.assertIs(admitted["zero_knowledge"], False)
            self.assertEqual(
                admitted["kernel_if_backend_down"], self.doc["kernel_if_backend_down"]
            )
            self.assertEqual(self.doc["kernel_if_backend_down"], "unchanged")

    def test_a_widened_claim_scope_is_refused(self) -> None:
        # The demotion cannot be talked out of the admission function.
        for scope in ("field-evidence", "record-integrity-only", ""):
            with self.assertRaises(ValueError, msg=scope):
                admit_guest("beam-b1-f2-1", claim_scope=scope)

    def test_the_guest_attests_arithmetic_and_not_evidence(self) -> None:
        guest = next(g for g in self.doc["allowed_guests"] if g["id"] == "beam-b1-f2-1")
        for demotion in ("evidence truth", "Gaussian update", "occupancy"):
            self.assertIn(demotion, guest["does_not_attest"])


class ZkvmNumericQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = _load("zkvm-numeric-queue-v1.json")

    def test_the_current_profile_is_one_the_code_admits(self) -> None:
        current = self.doc["current"]
        self.assertIn(current["arithmetic"], ADMITTED)
        admitted = admit_numeric_profile(
            {"arithmetic": current["arithmetic"], "guest_id": current["guest_id"]}
        )
        self.assertIs(admitted["admitted"], True)
        self.assertEqual(admitted["quantize_on"], "host")

    def test_the_current_guest_is_the_allowed_one(self) -> None:
        # Cross-artifact: the numeric queue may not name a guest the scope forbids.
        self.assertIn(self.doc["current"]["guest_id"], ALLOWED)

    def test_every_refused_arithmetic_is_actually_refused(self) -> None:
        for arithmetic in REFUSED:
            with self.assertRaises(ValueError, msg=arithmetic):
                admit_numeric_profile(
                    {"arithmetic": arithmetic, "guest_id": "beam-b1-f2-1"}
                )

    def test_the_two_refused_lists_are_different_vocabularies(self) -> None:
        # The artifact refuses computations (ieee754-geodesic, rk4-manifold);
        # the code refuses arithmetic profiles (ieee754, float64). Asserting one
        # against the other would be a false test, so this pins the distinction
        # instead, to stop a later reader writing that assertion.
        self.assertTrue(set(self.doc["refused"]).isdisjoint(REFUSED))
        self.assertTrue(set(self.doc["refused"]).isdisjoint(ADMITTED))
        self.assertTrue(set(self.doc["not_opened"]).isdisjoint(REFUSED | ADMITTED))

    def test_nothing_queued_is_already_claimed_as_implemented(self) -> None:
        queued = set(self.doc["not_opened"]) | set(self.doc["refused"])
        self.assertNotIn(self.doc["current"]["guest_id"], queued)


class Sp1GuestClaimTests(unittest.TestCase):
    """A claim shape with no proof in it, and it says so."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = _load("sp1-guest-claim-v0.json")

    def test_it_is_uninvoked_and_unproven(self) -> None:
        self.assertIs(self.doc["zk"], False)
        self.assertIs(self.doc["invoked"], False)
        self.assertIs(self.doc["allowed"], False)
        for empty in ("program_id", "input_digest", "output_digest"):
            self.assertIsNone(self.doc[empty], empty)

    def test_the_four_non_claims_are_present(self) -> None:
        non_claims = self.doc["non_claims"]
        self.assertIn("not a field observation", non_claims)
        self.assertIn("not an ApprovalRecord", non_claims)
        self.assertIn("not a Beam-B1 certificate", non_claims)
        self.assertIn(
            "not zero-knowledge unless zk is true and a proof is attached", non_claims
        )

    def test_its_allowed_flag_agrees_with_the_effort_gate(self) -> None:
        # Cross-artifact: the claim says allowed false and names the gate as its
        # authority, so the gate had better refuse sp1_zkvm.
        self.assertEqual(self.doc["authority"], "rust-effort-gate")
        decision = decide_satellite(load_effort_table(), "sp1_zkvm")
        self.assertIs(decision.allowed, False)
        self.assertEqual(decision.disposition, "REFUSE")
        self.assertIs(self.doc["allowed"], decision.allowed)


if __name__ == "__main__":
    unittest.main()
