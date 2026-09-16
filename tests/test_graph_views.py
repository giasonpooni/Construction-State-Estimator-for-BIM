"""Graph views describe objects we already have. They do not infer."""

from __future__ import annotations

import unittest

from gat.harness.atlas import office_a_atlas
from gat.harness.graph_views import (
    functional_ledger,
    opening_factorization,
    spectral_atlas,
)


class SpectralTests(unittest.TestCase):
    def test_atlas_has_a_laplacian_spectrum(self) -> None:
        report = spectral_atlas(office_a_atlas())
        self.assertEqual(report["schema"], "cse-spectral-atlas-v1")
        self.assertGreaterEqual(len(report["eigenvalues"]), 2)
        self.assertAlmostEqual(report["eigenvalues"][0], 0.0, places=6)


class FunctionalTests(unittest.TestCase):
    def test_one_next_world_is_functional(self) -> None:
        report = functional_ledger(
            [
                {"prior_world_digest": "aa", "result_world_digest": "bb", "event_hash": "e1"},
                {"prior_world_digest": "bb", "result_world_digest": "cc", "event_hash": "e2"},
            ]
        )
        self.assertTrue(report["functional"])
        self.assertEqual(len(report["transitions"]), 2)

    def test_two_next_worlds_is_a_fork(self) -> None:
        report = functional_ledger(
            [
                {"prior_world_digest": "aa", "result_world_digest": "bb"},
                {"prior_world_digest": "aa", "result_world_digest": "cc"},
            ]
        )
        self.assertFalse(report["functional"])
        self.assertEqual(len(report["forks"]), 1)


class FactorTests(unittest.TestCase):
    def test_declaration_does_not_claim_inference(self) -> None:
        document = opening_factorization()
        self.assertFalse(document["sum_product"])
        self.assertEqual(document["estimator"], "dense-GAT")


if __name__ == "__main__":
    unittest.main()
