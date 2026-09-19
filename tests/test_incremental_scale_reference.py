"""The dense cost reference is checked against the code that produced it.

validation/incremental-scale-reference-v1.json is the dense-path cost study the
sparse-belief exit test requires as its first half. It was read by nothing, so
nothing noticed whether it still described this code.

What is asserted here is only what is machine-independent. The artifact says of
itself "environment-specific-reference-not-regression-threshold", so asserting
its seconds would be asserting somebody else's laptop. What can be checked is
that its description of the synthetic model matches what the code actually
builds, and that its recorded cliffs follow from its own measurements under its
own stated definition.

Timing is deliberately not measured here. At small sizes the incremental path is
slower than the complete one -- the bookkeeping dominates -- so a "faster"
assertion would be false as well as flaky.

stdlib unittest only.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from gat.demo.incremental_scale import synthetic_storey_module
from gat.engine.executor import World

_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = _ROOT / "validation" / "incremental-scale-reference-v1.json"
ONE_SECOND = 1.0


class ScaleReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        cls.measurements = cls.reference["measurements"]

    def test_it_declares_itself_a_reference_not_a_threshold(self) -> None:
        self.assertEqual(self.reference["format"], "gat-incremental-scale-reference-v1")
        self.assertIn("not-regression-threshold", self.reference["status"])
        # If this ever became a threshold it would need the host recorded, and
        # the host is explicitly not recorded beyond a note.
        self.assertIn("hardware", self.reference["runtime"])

    def test_the_synthetic_model_description_matches_the_code(self) -> None:
        claim = self.reference["synthetic_model"]
        per_storey_raw = claim["raw_variables_per_storey"]
        per_storey_derived = claim["derived_variables_per_storey"]
        for storeys in (1, 4, 16):
            world = World.compile(synthetic_storey_module(storeys))
            raw = world.binding.n_raw
            derived = world.binding.n_full - raw
            self.assertEqual(raw, per_storey_raw * storeys, f"{storeys} storeys")
            self.assertEqual(derived, per_storey_derived * storeys, f"{storeys} storeys")

    def test_the_declared_representation_is_the_dense_oracle(self) -> None:
        self.assertEqual(
            self.reference["synthetic_model"]["covariance_representation"],
            "dense-float64",
        )

    def test_full_variables_are_consistent_with_the_storey_counts(self) -> None:
        claim = self.reference["synthetic_model"]
        per_storey = claim["raw_variables_per_storey"] + claim["derived_variables_per_storey"]
        for row in self.measurements:
            self.assertEqual(row["full_variables"], row["storeys"] * per_storey)

    def test_the_recorded_cliff_follows_from_its_own_definition(self) -> None:
        self.assertIn("at or above 1.0 seconds", self.reference["one_second_cliff_definition"])
        cliffs = self.reference["observed_cliffs"]
        complete = next(
            (
                row["storeys"]
                for row in self.measurements
                if row["complete_pushforward_seconds"] >= ONE_SECOND
            ),
            None,
        )
        self.assertEqual(cliffs["complete_pushforward_storeys"], complete)

    def test_the_incremental_cliff_is_not_earlier_than_the_complete_one(self) -> None:
        cliffs = self.reference["observed_cliffs"]
        self.assertGreaterEqual(
            cliffs["verified_incremental_pipeline_storeys"],
            cliffs["complete_pushforward_storeys"],
            "an incremental path that hits one second sooner than the complete "
            "one would not be an incremental path",
        )

    def test_measurements_are_ordered_and_grow(self) -> None:
        sizes = [row["storeys"] for row in self.measurements]
        self.assertEqual(sizes, sorted(sizes))
        seconds = [row["complete_pushforward_seconds"] for row in self.measurements]
        self.assertEqual(seconds, sorted(seconds), "dense cost must be monotonic in n")
        # Superlinear: doubling n must cost more than double.
        for earlier, later in zip(self.measurements, self.measurements[1:]):
            if later["storeys"] == 2 * earlier["storeys"]:
                self.assertGreater(
                    later["complete_pushforward_seconds"],
                    2.0 * earlier["complete_pushforward_seconds"],
                )

    def test_every_row_records_what_the_incremental_path_recomputed(self) -> None:
        # The claim that makes the incremental path auditable rather than magic.
        for row in self.measurements:
            self.assertGreater(row["covariance_left_rows_recomputed"], 0)
            self.assertGreater(row["full_covariance_rows_recomputed"], 0)
            self.assertLess(row["covariance_left_rows_recomputed"], row["full_variables"])


if __name__ == "__main__":
    unittest.main()
