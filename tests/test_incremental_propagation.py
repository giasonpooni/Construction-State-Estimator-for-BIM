"""Incremental pushforward equivalence, selectivity, and scale probe tests."""

from __future__ import annotations

import tempfile
import unittest

import numpy as np

from gat.demo.incremental_scale import (
    coupled_storey_module,
    dense_state_bytes,
    measure_size,
    run_probe,
    storeys_for_dense_budget,
)
from gat.engine.transform import ScaleParameter, ShiftParameter
from gat.session import GatSession


MODEL = "gat/demo/model.ifc"


class IncrementalPropagationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = GatSession.load_ifc(MODEL)

    def assert_matches_complete(self, transformation) -> None:
        world = self.session.world
        belief = transformation.apply(world.binding, world.belief)
        complete = world.with_belief(belief)
        incremental, stats = world.with_belief_incremental(belief)

        np.testing.assert_array_equal(incremental.full.mu, complete.full.mu)
        np.testing.assert_array_equal(incremental.full.sigma, complete.full.sigma)
        self.assertEqual(incremental.full.index.vars, complete.full.index.vars)
        self.assertEqual(stats.mode, "incremental")
        self.assertLess(
            stats.full_covariance_rows_recomputed,
            stats.full_variable_count,
        )

    def test_local_shift_recomputes_only_dependency_closed_rows(self) -> None:
        transformation = ShiftParameter(
            self.session.var("Wall-Party", "Width"),
            0.001,
        )
        result = self.session.run(transformation)
        stats = result.propagation

        self.assertIsNotNone(stats)
        self.assertEqual(stats.mode, "incremental")
        self.assertEqual(stats.raw_mean_rows_changed, 1)
        self.assertEqual(stats.raw_covariance_rows_changed, 0)
        self.assertEqual(
            stats.derived_value_rows_recomputed,
            len(result.affected),
        )
        self.assertEqual(
            stats.covariance_left_rows_recomputed,
            len(result.affected),
        )
        self.assertEqual(stats.full_covariance_rows_recomputed, len(result.affected))

    def test_covariance_change_reports_global_cached_product_refresh(self) -> None:
        transformation = ScaleParameter(
            self.session.var("Wall-Party", "Width"),
            1.01,
        )
        result = self.session.run(transformation)
        stats = result.propagation

        self.assertIsNotNone(stats)
        self.assertEqual(stats.mode, "incremental")
        self.assertEqual(stats.raw_mean_rows_changed, 1)
        self.assertEqual(stats.raw_covariance_rows_changed, 1)
        self.assertEqual(
            stats.covariance_left_rows_recomputed,
            stats.full_variable_count,
        )
        self.assertEqual(
            stats.full_covariance_rows_recomputed,
            len(result.affected) + 1,
        )

    def test_shift_and_scale_match_complete_pushforward(self) -> None:
        self.assert_matches_complete(
            ShiftParameter(self.session.var("Wall-Party", "Width"), 0.001)
        )
        self.assert_matches_complete(
            ScaleParameter(self.session.var("Wall-Party", "Width"), 1.01)
        )


class IncrementalScaleProbeTests(unittest.TestCase):
    def test_synthetic_probe_has_two_row_dependency_scope(self) -> None:
        row = measure_size(16, repeats=1)
        work = row["incremental_work"]

        self.assertEqual(row["raw_variables"], 16)
        self.assertEqual(row["derived_variables"], 32)
        self.assertEqual(row["full_variables"], 48)
        self.assertEqual(work["mode"], "incremental")
        self.assertEqual(work["derived_value_rows_recomputed"], 2)
        self.assertEqual(work["covariance_left_rows_recomputed"], 2)
        self.assertEqual(work["full_covariance_rows_recomputed"], 2)
        self.assertLessEqual(row["max_abs_covariance_error"], 1e-12)

    def test_dense_memory_limit_is_analytical_and_monotone(self) -> None:
        one_gib = storeys_for_dense_budget(1024**3)
        four_gib = storeys_for_dense_budget(4 * 1024**3)
        self.assertGreater(four_gib, one_gib)
        self.assertLessEqual(dense_state_bytes(one_gib, 3 * one_gib), 1024**3)
        self.assertGreater(
            dense_state_bytes(one_gib + 1, 3 * (one_gib + 1)),
            1024**3,
        )

    def test_probe_writes_machine_readable_result_without_timing_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/probe.json"
            result = run_probe(
                (4, 8),
                repeats=1,
                time_cliff_seconds=60.0,
                output_path=output,
                quiet=True,
            )
        self.assertEqual(result["format"], "gat-incremental-scale-probe-v1")
        self.assertIsNone(result["first_measured_complete_pushforward_cliff_storeys"])
        self.assertIsNone(result["first_measured_verified_incremental_cliff_storeys"])
        self.assertEqual(len(result["measurements"]), 2)


class CoupledShapeTests(unittest.TestCase):
    """The speedup is a property of the shape, not of the engine.

    Until the coupled shape existed the probe could only build worlds where
    one change touches two rows however large the world is -- the easy case,
    by construction, and not the one GAT's coupling story is about.
    """

    SIZE = 120

    def _row(self, model: str) -> dict:
        return measure_size(self.SIZE, repeats=2, model=model)

    def test_an_independent_world_stays_almost_diagonal(self) -> None:
        row = self._row("independent")
        self.assertLess(row["full_covariance_offdiagonal_density"], 0.05)
        self.assertEqual(row["incremental_work"]["full_covariance_rows_recomputed"], 2)

    def test_a_shared_variable_makes_the_covariance_dense(self) -> None:
        row = self._row("coupled-local")
        self.assertGreater(row["full_covariance_offdiagonal_density"], 0.30)

    def test_a_local_change_stays_local_even_when_coupled(self) -> None:
        row = self._row("coupled-local")
        self.assertEqual(row["incremental_work"]["full_covariance_rows_recomputed"], 2)
        self.assertIn("Length", row["changed_variable"])

    def test_changing_the_shared_height_invalidates_every_derived_row(self) -> None:
        row = self._row("coupled-shared")
        self.assertIn("ClearHeight", row["changed_variable"])
        self.assertEqual(
            row["incremental_work"]["full_covariance_rows_recomputed"],
            2 * self.SIZE,
        )

    def test_the_probe_records_which_shape_and_which_variable(self) -> None:
        """A speedup without them is not a claim anyone can check."""
        with tempfile.TemporaryDirectory() as directory:
            result = run_probe(
                (8,),
                repeats=1,
                time_cliff_seconds=60.0,
                output_path=f"{directory}/probe.json",
                quiet=True,
                model="coupled-shared",
            )
        self.assertEqual(result["synthetic_model"]["shape"], "coupled-shared")
        self.assertIn("ClearHeight", result["measurements"][0]["changed_variable"])
        self.assertIn("slower", result["conclusion_note"])

    def test_an_unknown_shape_is_refused(self) -> None:
        for call in (
            lambda: measure_size(8, 1, "no-such-shape"),
            lambda: run_probe((8,), repeats=1, quiet=True, model="no-such-shape"),
        ):
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()

    def test_the_coupled_builder_refuses_a_nonsense_size(self) -> None:
        for bad in (0, -1, True, 2.5):
            with self.subTest(walls=bad):
                with self.assertRaises(ValueError):
                    coupled_storey_module(bad)


if __name__ == "__main__":
    unittest.main()
