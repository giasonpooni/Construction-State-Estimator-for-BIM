from __future__ import annotations

import os
from types import SimpleNamespace

from dataclasses import replace
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import gat.demo
from gat.engine.decision import DecisionVerdict, assess_decision
from gat.engineering.beam import BeamBendingCheck, BeamBendingEvaluator
from gat.errors import ProofManifestError
from gat.session import GatSession
from gat.demo.beam_assurance import run_beam_assurance
from gat.ledger import read_ledger
from gat.proof_manifest import computation_proof_public_values_digest
from gat.sp1_beam import (
    SP1_BEAM_CIRCUIT_VERSION,
    SP1_BEAM_NUMERIC_PROFILE_DIGEST,
    SP1_BEAM_PROOF_TYPE,
    SP1_BEAM_RECEIPT_FORMAT,
    SP1_BEAM_VERSION,
    Sp1BeamClaim,
    Sp1BeamClaimInput,
    Sp1BeamProofReceipt,
    Sp1BeamPublicValues,
    Sp1BeamRequest,
    read_sp1_beam_request,
    build_sp1_beam_claim,
    sp1_beam_assessment_record,
    sp1_beam_numeric_contract,
    write_sp1_beam_request,
)


KNOWN_COMPUTATION_DIGEST = (
    "1443b90bc95f146a0a4c1e8e4beeb7db9c7cd59e9431f05e91958bb6c97e54e6"
)
KNOWN_PUBLIC_VALUES = (
    "6761742d7370312d6265616d2d7075626c69632d763100"
    + "55" * 32
    + KNOWN_COMPUTATION_DIGEST
    + "00000000000000000000004bab827200"
    + "0000000000000000000000441a5bcd00"
    + "00000000000000000000004614ff8200"
    + "00"
)


def known_input() -> Sp1BeamClaimInput:
    return Sp1BeamClaimInput(
        325_000,
        1_000_000,
        301_000_000_000,
        900_000,
        SP1_BEAM_NUMERIC_PROFILE_DIGEST,
        "11" * 32,
        "22" * 32,
        "33" * 32,
        "44" * 32,
    )


class Sp1BeamArithmeticTests(unittest.TestCase):
    def test_python_matches_the_rust_known_vector(self) -> None:
        claim = Sp1BeamClaim.evaluate(known_input())
        self.assertEqual(claim.nominal_milli_n_mm, 325_000_000_000)
        self.assertEqual(claim.available_milli_n_mm, 292_500_000_000)
        self.assertEqual(claim.verdict, "FAIL")
        self.assertEqual(claim.computation_digest, KNOWN_COMPUTATION_DIGEST)
        public = Sp1BeamPublicValues(
            "55" * 32,
            claim.computation_digest,
            claim.nominal_milli_n_mm,
            claim.available_milli_n_mm,
            claim.input.factored_demand_milli_n_mm,
            claim.verdict,
        )
        self.assertEqual(public.to_bytes().hex(), KNOWN_PUBLIC_VALUES)
        self.assertEqual(Sp1BeamPublicValues.from_bytes(public.to_bytes()), public)

    def test_claim_rejects_profile_phi_output_and_overflow_drift(self) -> None:
        with self.assertRaises(ProofManifestError):
            replace(known_input(), resistance_factor_ppm=899_999)
        with self.assertRaises(ProofManifestError):
            replace(known_input(), numeric_profile_digest="00" * 32)
        claim = Sp1BeamClaim.evaluate(known_input())
        with self.assertRaises(ProofManifestError):
            replace(claim, available_milli_n_mm=claim.available_milli_n_mm + 1)
        overflowing = replace(
            known_input(),
            yield_strength_milli_mpa=(1 << 64) - 1,
            plastic_section_modulus_mm3=(1 << 64) - 1,
        )
        with self.assertRaisesRegex(ProofManifestError, "numerator overflows"):
            Sp1BeamClaim.evaluate(overflowing)

    def test_request_is_strict_and_roundtrips(self) -> None:
        request = Sp1BeamRequest(
            2,
            "55" * 32,
            sp1_beam_numeric_contract(),
            Sp1BeamClaim.evaluate(known_input()),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            written = write_sp1_beam_request(request, path)
            self.assertEqual(read_sp1_beam_request(path), request)
            self.assertEqual(written, hashlib.sha256(path.read_bytes()).hexdigest())
            value = json.loads(path.read_text(encoding="utf-8"))
            circuit_drift = copy.deepcopy(value)
            circuit_drift["sp1_circuit_version"] = "v6.0.0"
            path.write_text(json.dumps(circuit_drift), encoding="utf-8")
            with self.assertRaisesRegex(ProofManifestError, "circuit version"):
                read_sp1_beam_request(path)
            value["claim"]["output"]["verdict"] = "PASS"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ProofManifestError):
                read_sp1_beam_request(path)

    def test_receipt_requires_exact_types_and_consistent_public_values(self) -> None:
        receipt = {
            "format": SP1_BEAM_RECEIPT_FORMAT,
            "schema_version": 1,
            "sp1_version": SP1_BEAM_VERSION,
            "sp1_circuit_version": SP1_BEAM_CIRCUIT_VERSION,
            "proof_type": SP1_BEAM_PROOF_TYPE,
            "program_digest": "66" * 32,
            "verifying_key_digest": "77" * 32,
            "proof_artifact_digest": "88" * 32,
            "public_values_hex": KNOWN_PUBLIC_VALUES,
            "public_statement_digest": "55" * 32,
            "computation_result_digest": KNOWN_COMPUTATION_DIGEST,
            "proof_verified": True,
            "cycles": None,
        }
        parsed = Sp1BeamProofReceipt.from_dict(receipt)
        self.assertTrue(parsed.proof_verified)
        wrong_type = copy.deepcopy(receipt)
        wrong_type["sp1_version"] = 640
        with self.assertRaises(ProofManifestError):
            Sp1BeamProofReceipt.from_dict(wrong_type)
        wrong_circuit = copy.deepcopy(receipt)
        wrong_circuit["sp1_circuit_version"] = "v6.0.0"
        with self.assertRaisesRegex(ProofManifestError, "circuit version"):
            Sp1BeamProofReceipt.from_dict(wrong_circuit)
        inconsistent = copy.deepcopy(receipt)
        inconsistent["public_statement_digest"] = "99" * 32
        with self.assertRaises(ProofManifestError):
            Sp1BeamProofReceipt.from_dict(inconsistent)

    def test_reference_chain_emits_the_exact_ledger_bound_guest_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_beam_assurance(directory, quiet=True)
            request = read_sp1_beam_request(Path(directory) / "beam_sp1_request.json")
            ledger = read_ledger(Path(directory) / "beam_ledger.json")
            expected = computation_proof_public_values_digest(
                ledger,
                request.transition_event_seq,
                numeric_contract=request.numeric_contract,
                model_contract_digest=request.claim.input.model_contract_digest,
                validation_profile_digest=request.claim.input.validation_profile_digest,
                computation_result_digest=request.claim.computation_digest,
                evidence_commitments=(
                    request.claim.input.evidence_digest,
                    request.claim.input.evidence_source_digest,
                ),
            )
            self.assertEqual(request.public_statement_digest, expected)
            fixed_assessment = ledger.events[-1].operation
            self.assertEqual(
                fixed_assessment["details"]["computation"]["computation_digest"],
                request.claim.computation_digest,
            )


class ProofVerdictIsNotTheRuntimeVerdictTests(unittest.TestCase):
    """A signed PASS beside an UNRESOLVED disposition must not read as agreement.

    ``build_sp1_beam_claim`` quantizes ``world.belief.mean(...)``
    (gat/sp1_beam.py:479-480) and the module contains no reference to a
    sigma anywhere. So the claim's verdict flips at P = 0.5 -- it is PASS
    exactly when the posterior MEAN capacity clears the demand -- while this
    runtime's own rule wants the decision's declared confidence. Measured on
    gat/demo/beam_model.ifc, DesignMomentCapacity 315000.0 +- 7858.9 N*m:

        demand      p_satisfies   runtime      claim
        300000 N*m      0.9718     SATISFIED    PASS
        310000 N*m      0.7377     UNRESOLVED   PASS   <-- diverges
        320000 N*m      0.2623     UNRESOLVED   FAIL

    Nothing is miscomputed. The guest proves what its docstring says, and
    ``claim_limits.proves_gaussian_update`` was always False. The hazard is
    that the artifact carried one word, "PASS", and a reader had to already
    know that the criterion kind above it meant mean-capacity. So the record
    now carries the probabilistic verdict beside the deterministic one, and
    marks the band where they disagree.
    """

    MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "beam_model.ifc")

    class _Evidence:
        """Minimal stand-in: build_sp1_beam_claim reads only these."""

        def __init__(self, beam) -> None:
            self.subject = SimpleNamespace(entity=beam)
            self.source_digest = "1" * 64

        def digest(self) -> str:
            return "0" * 64

    def _record_for(self, demand: float):
        session = GatSession.load_ifc(self.MODEL)
        beam = session.entity_by_name("Beam-B1")
        check = BeamBendingCheck(beam, float(demand), 0.95, f"demand {demand}")
        result = BeamBendingEvaluator().evaluate(session.world, check)
        evidence = self._Evidence(beam)
        claim = build_sp1_beam_claim(session.world, result, evidence)
        record = sp1_beam_assessment_record(session.world, result, evidence, claim)
        return claim, record, assess_decision(session.world, check.decision())

    def test_the_record_carries_the_belief_verdict_too(self) -> None:
        claim, record, assessment = self._record_for(300_000)
        belief = record.details["belief_verdict"]
        self.assertEqual(belief["verdict"], assessment.verdict.value)
        self.assertAlmostEqual(belief["p_satisfies"], assessment.p_satisfies, places=12)
        self.assertEqual(belief["confidence"], 0.95)
        self.assertIn("target_sigma_n_m", belief)
        self.assertGreater(belief["target_sigma_n_m"], 0.0)

    def test_the_divergence_band_is_marked(self) -> None:
        """The whole point: at 310 kN*m the claim says PASS and the runtime
        says UNRESOLVED, and the record has to say that out loud."""
        claim, record, assessment = self._record_for(310_000)
        self.assertEqual(claim.verdict, "PASS")
        self.assertEqual(assessment.verdict, DecisionVerdict.UNRESOLVED)
        self.assertTrue(record.details["belief_verdict"]["diverges"])
        self.assertLess(record.details["belief_verdict"]["p_satisfies"], 0.95)

    def test_agreement_is_marked_as_agreement(self) -> None:
        for demand in (250_000, 300_000, 320_000):
            with self.subTest(demand=demand):
                claim, record, assessment = self._record_for(demand)
                agree = (assessment.verdict is DecisionVerdict.SATISFIED) == (
                    claim.verdict == "PASS"
                )
                self.assertTrue(agree, "fixture moved; pick another demand")
                self.assertFalse(record.details["belief_verdict"]["diverges"])

    def test_the_claim_still_flips_at_the_mean_not_the_confidence(self) -> None:
        """Pinning the actual behaviour, so that if the circuit ever does
        learn about sigma this test fails and says where to look."""
        _, _, low = self._record_for(310_000)
        self.assertGreater(low.p_satisfies, 0.5)
        self.assertLess(low.p_satisfies, 0.95)
        claim, _, _ = self._record_for(310_000)
        self.assertEqual(claim.verdict, "PASS")

    def test_the_limits_name_what_a_reader_would_assume(self) -> None:
        _, record, _ = self._record_for(300_000)
        limits = record.details["claim_limits"]
        self.assertFalse(limits["proves_declared_confidence"])
        self.assertFalse(limits["proves_gaussian_update"])
        self.assertEqual(
            record.details["criterion"]["kind"],
            "deterministic-fixed-point-mean-capacity",
        )



if __name__ == "__main__":
    unittest.main()
