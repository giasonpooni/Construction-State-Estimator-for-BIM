"""A sequence of instruments composes only where the axioms survive the join.

The stitcher computes nothing and imports no companion. It reads typed artifacts
and refuses at the arrow: a rectangular sensitivity Jacobian is not a plant, a
verdict on one matrix does not transfer to another, a proof status is not a
stability verdict, and a certificate never authorizes.

The vocabularies here are the companion's real ones, which is the whole point.
lyapunov.runtime.verdict returns lower-case certified / violated / outside-level
/ inconclusive; lyapunov.host_callback.ProofStatus is upper-case NOT_CHECKED /
INVALID / VERIFIED and describes an SP1 attachment. Conflating them would let a
checked-arithmetic claim stand in for a stability claim. The agreement tests at
the bottom run against the installed companion when there is one.

stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from gat.harness.stitch import (
    CERTIFICATE_VERDICTS,
    MAX_KRONECKER_DIM,
    PLANT_SCHEMA,
    PROOF_STATUSES,
    RECEIPT_SCHEMA,
    SUPPORTING_VERDICTS,
    StitchError,
    read_plant,
    read_receipt,
    stitch,
    stitch_files,
)


def lyapunov_available() -> bool:
    try:
        return importlib.util.find_spec("lyapunov") is not None
    except (ImportError, ValueError):
        return False


def _plant(matrix=None, **kwargs) -> dict:
    document = {
        "schema": PLANT_SCHEMA,
        "name": "A=J(x*)",
        "time": "continuous",
        "matrix": matrix if matrix is not None else [[-1.0, 0.5], [0.0, -2.0]],
        "source": "JSPT jacobian_at",
    }
    document.update(kwargs)
    return document


def _receipt(plant_document: dict, **kwargs) -> dict:
    plant = read_plant(plant_document)
    document = {
        "schema": RECEIPT_SCHEMA,
        "plant_digest": plant.digest,
        "verdict": "certified",
        "dimension": plant.dimension,
        "source": "PLSR runtime.verdict",
    }
    document.update(kwargs)
    return document


class PlantLawTests(unittest.TestCase):
    def test_a_square_finite_matrix_is_a_plant(self) -> None:
        plant = read_plant(_plant())
        self.assertEqual(plant.dimension, 2)
        self.assertEqual(len(plant.digest), 64)

    def test_the_digest_is_a_function_of_the_matrix_and_time_domain(self) -> None:
        same = read_plant(_plant()).digest
        self.assertEqual(read_plant(_plant(name="other")).digest, same)
        self.assertNotEqual(read_plant(_plant(time="discrete")).digest, same)
        self.assertNotEqual(read_plant(_plant([[-1.0, 0.5], [0.0, -2.5]])).digest, same)

    def test_a_rectangular_jacobian_is_not_a_plant(self) -> None:
        with self.assertRaisesRegex(StitchError, "square"):
            read_plant(_plant([[-1.0, 0.5, 0.1], [0.0, -2.0, 0.3]]))

    def test_a_ragged_matrix_is_refused(self) -> None:
        with self.assertRaisesRegex(StitchError, "ragged"):
            read_plant(_plant([[-1.0, 0.5], [0.0]]))

    def test_a_non_finite_entry_is_refused(self) -> None:
        with self.assertRaisesRegex(StitchError, "finite"):
            read_plant(_plant([[float("inf"), 0.0], [0.0, -1.0]]))

    def test_a_boolean_is_not_a_number(self) -> None:
        with self.assertRaisesRegex(StitchError, "non-numeric"):
            read_plant(_plant([[True, 0.0], [0.0, -1.0]]))

    def test_the_certificate_law_caps_the_dimension(self) -> None:
        big = [[(-1.0 if i == j else 0.0) for j in range(MAX_KRONECKER_DIM + 1)]
               for i in range(MAX_KRONECKER_DIM + 1)]
        with self.assertRaisesRegex(StitchError, "MAX_KRONECKER_DIM"):
            read_plant(_plant(big))
        edge = [[(-1.0 if i == j else 0.0) for j in range(MAX_KRONECKER_DIM)]
                for i in range(MAX_KRONECKER_DIM)]
        self.assertEqual(read_plant(_plant(edge)).dimension, MAX_KRONECKER_DIM)

    def test_an_unknown_time_domain_is_refused(self) -> None:
        with self.assertRaisesRegex(StitchError, "time domain"):
            read_plant(_plant(time="sampled"))

    def test_a_wrong_schema_is_refused(self) -> None:
        with self.assertRaisesRegex(StitchError, "schema"):
            read_plant(_plant(schema="something-else"))


class ReceiptLawTests(unittest.TestCase):
    def test_a_shipped_verdict_reads(self) -> None:
        for verdict in sorted(CERTIFICATE_VERDICTS):
            receipt = read_receipt(_receipt(_plant(), verdict=verdict))
            self.assertEqual(receipt.verdict, verdict)
            self.assertEqual(receipt.supports, verdict in SUPPORTING_VERDICTS)

    def test_only_certified_supports_anything(self) -> None:
        self.assertEqual(SUPPORTING_VERDICTS, frozenset({"certified"}))

    def test_a_proof_status_is_not_a_certificate_verdict(self) -> None:
        # The conflation this module exists to prevent.
        for status in sorted(PROOF_STATUSES):
            with self.assertRaisesRegex(StitchError, "proof status"):
                read_receipt(_receipt(_plant(), verdict=status))

    def test_the_two_vocabularies_are_disjoint(self) -> None:
        self.assertTrue(CERTIFICATE_VERDICTS.isdisjoint(PROOF_STATUSES))

    def test_a_discussed_but_unshipped_verdict_is_refused(self) -> None:
        for proposed in ("LYAPUNOV_SAMPLE", "SUFFICIENT_COMMON_QUADRATIC", "REFUSE"):
            with self.assertRaisesRegex(StitchError, "not a shipped certificate verdict"):
                read_receipt(_receipt(_plant(), verdict=proposed))

    def test_a_proof_status_field_must_still_be_valid(self) -> None:
        with self.assertRaisesRegex(StitchError, "proof_status"):
            read_receipt(_receipt(_plant(), proof_status="certified"))
        receipt = read_receipt(_receipt(_plant(), proof_status="VERIFIED"))
        self.assertEqual(receipt.proof_status, "VERIFIED")

    def test_a_global_claim_needs_a_declared_vertex_set(self) -> None:
        with self.assertRaisesRegex(StitchError, "vertex set"):
            read_receipt(_receipt(_plant(), global_claim=True))
        receipt = read_receipt(_receipt(_plant(), global_claim=True, vertex_set=4))
        self.assertTrue(receipt.global_claim)
        self.assertEqual(receipt.vertex_set, 4)


class JoinTests(unittest.TestCase):
    def test_a_matching_sequence_composes(self) -> None:
        plant = _plant()
        record = stitch(plant, _receipt(plant))
        self.assertIs(record["composes"], True)
        self.assertEqual(record["claim_scope"], "record-integrity-only")
        self.assertEqual([s["stage"] for s in record["sequence"]],
                         ["plant", "certificate", "disposition"])

    def test_a_verdict_does_not_transfer_between_matrices(self) -> None:
        plant = _plant()
        other = _receipt(_plant([[-1.0, 0.5], [0.0, -2.5]]))
        with self.assertRaisesRegex(StitchError, "does not certify this plant"):
            stitch(plant, other)

    def test_a_dimension_mismatch_is_refused(self) -> None:
        plant = _plant()
        with self.assertRaisesRegex(StitchError, "dimension"):
            stitch(plant, _receipt(plant, dimension=3))

    def test_a_citation_may_not_authorize(self) -> None:
        plant = _plant()
        with self.assertRaisesRegex(StitchError, "may_authorize false"):
            stitch(plant, _receipt(plant), {"may_authorize": True})

    def test_a_citation_must_state_may_authorize_at_all(self) -> None:
        plant = _plant()
        with self.assertRaisesRegex(StitchError, "must state may_authorize"):
            stitch(plant, _receipt(plant), {"world_digest": "0" * 64})

    def test_an_unsupporting_verdict_may_not_become_a_support_code(self) -> None:
        plant = _plant()
        for verdict in sorted(CERTIFICATE_VERDICTS - SUPPORTING_VERDICTS):
            with self.assertRaisesRegex(StitchError, "support_code"):
                stitch(
                    plant,
                    _receipt(plant, verdict=verdict),
                    {"may_authorize": False, "support_code": "stability"},
                )

    def test_what_the_record_refuses_to_claim(self) -> None:
        plant = _plant()
        record = stitch(plant, _receipt(plant))
        text = " ".join(record["not_claimed"])
        self.assertIn("not an ACCEPT", text)
        self.assertIn("not a global proof", text)
        self.assertIn("proof_status is about arithmetic", text)
        self.assertIn("no device or backend", text)


class FileTests(unittest.TestCase):
    def test_stitch_files_reads_a_sequence_from_disk(self) -> None:
        plant = _plant()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "A.json").write_text(json.dumps(plant), encoding="utf-8")
            (root / "r.json").write_text(json.dumps(_receipt(plant)), encoding="utf-8")
            record = stitch_files(root / "A.json", root / "r.json")
            self.assertIs(record["composes"], True)

    def test_malformed_json_is_a_refusal_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "A.json").write_text("{not json", encoding="utf-8")
            (root / "r.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(StitchError, "not valid JSON"):
                stitch_files(root / "A.json", root / "r.json")


class CliTests(unittest.TestCase):
    def test_a_type_miss_exits_two(self) -> None:
        from gat.cli import main

        plant = _plant([[-1.0, 0.5, 0.1], [0.0, -2.0, 0.3]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "A.json").write_text(json.dumps(plant), encoding="utf-8")
            (root / "r.json").write_text(
                json.dumps({"schema": RECEIPT_SCHEMA, "plant_digest": "0" * 64,
                            "verdict": "certified", "dimension": 3, "source": "x"}),
                encoding="utf-8",
            )
            self.assertEqual(main(["stitch", str(root / "A.json"), str(root / "r.json")]), 2)

    def test_a_composing_sequence_exits_zero(self) -> None:
        from gat.cli import main

        plant = _plant()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "A.json").write_text(json.dumps(plant), encoding="utf-8")
            (root / "r.json").write_text(json.dumps(_receipt(plant)), encoding="utf-8")
            self.assertEqual(
                main(["stitch", str(root / "A.json"), str(root / "r.json"), "--json"]), 0
            )


@unittest.skipUnless(lyapunov_available(), "companion PLSR clone is not importable")
class CompanionAgreementTests(unittest.TestCase):
    """The mirrored law and vocabulary must equal the companion's own."""

    def test_the_dimension_cap_matches_the_companion_constitution(self) -> None:
        from lyapunov.constitution import MAX_KRONECKER_DIM as upstream

        self.assertEqual(MAX_KRONECKER_DIM, upstream)

    def test_the_proof_statuses_match_the_companion_literal(self) -> None:
        import typing

        from lyapunov.host_callback import ProofStatus

        self.assertEqual(set(typing.get_args(ProofStatus)), set(PROOF_STATUSES))

    def test_a_real_verdict_is_a_verdict_this_stitcher_accepts(self) -> None:
        import numpy as np
        from lyapunov import certificate_for_plant, plant_from_jacobian
        from lyapunov.runtime import verdict as lyapunov_verdict

        matrix = [[-1.0, 0.5], [0.0, -2.0]]
        upstream_plant = plant_from_jacobian(np.array(matrix))
        certificate = certificate_for_plant(upstream_plant)
        upstream = lyapunov_verdict(upstream_plant, certificate, np.array([1.0, 1.0]))
        self.assertIn(upstream.status, CERTIFICATE_VERDICTS)

        plant = _plant(matrix)
        record = stitch(plant, _receipt(plant, verdict=upstream.status))
        self.assertIs(record["composes"], True)

    def test_the_companion_refuses_a_rectangular_plant_too(self) -> None:
        # The square axiom is enforced on both sides of the join, not just here.
        import numpy as np
        from lyapunov import plant_from_jacobian

        with self.assertRaises(ValueError):
            plant_from_jacobian(np.array([[-1.0, 0.5, 0.1], [0.0, -2.0, 0.3]]))


if __name__ == "__main__":
    unittest.main()
