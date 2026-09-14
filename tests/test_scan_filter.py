"""A reduced scan must say what was removed, and by what rule.

A real capture is millions of returns over a whole site; the registrar
measures at ~115 points per second. Reduction is unavoidable, so it has to be
evidence rather than housekeeping: every step records its method, parameters
and loss, and the result carries both the source digest and its own.

The ordering tests are the important ones. Downsampling concentrates
outliers, which is the opposite of the intuitive order, and getting it wrong
silently produced a 39x worse pose on the measured case below.
"""

from __future__ import annotations

import unittest

import numpy as np

from gat.errors import ScanArtifactError
from gat.geometry import scan_filter as F


def _wall_with_clutter(
    n_surface: int = 4000, n_clutter: int = 200, seed: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """A thin planar surface plus isolated returns away from it."""
    rng = np.random.default_rng(seed)
    surface = np.column_stack(
        [
            rng.uniform(0.0, 5.0, n_surface),
            rng.normal(0.0, 0.004, n_surface),
            rng.uniform(0.0, 3.0, n_surface),
        ]
    )
    clutter = rng.uniform(-2.0, 7.0, size=(n_clutter, 3))
    return surface, clutter


class ProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        surface, clutter = _wall_with_clutter()
        self.cloud = np.vstack([surface, clutter])

    def test_a_chain_binds_to_the_cloud_it_started_from(self) -> None:
        chain = F.voxel_downsample(F.begin(self.cloud), 0.05)
        self.assertEqual(chain.source_digest, F.scan_digest(self.cloud))
        self.assertNotEqual(chain.digest, chain.source_digest)

    def test_every_step_records_what_it_cost(self) -> None:
        chain = F.density_outlier_removal(
            F.voxel_downsample(F.begin(self.cloud), 0.05), 0.15, 4
        )
        record = chain.to_dict()
        self.assertEqual(record["format"], F.FILTER_FORMAT)
        self.assertEqual(record["source_point_count"], self.cloud.shape[0])
        self.assertEqual(len(record["steps"]), 2)
        for step in record["steps"]:
            with self.subTest(method=step["method"]):
                self.assertEqual(
                    step["dropped"], step["points_in"] - step["points_out"]
                )
                self.assertIn("parameters", step)

    def test_a_step_can_never_create_points(self) -> None:
        with self.assertRaises(ValueError):
            F.FilterStep("invented", {}, 10, 11)

    def test_filtering_is_deterministic(self) -> None:
        first = F.prepare_for_pose(self.cloud)
        second = F.prepare_for_pose(self.cloud)
        self.assertEqual(first.digest, second.digest)
        np.testing.assert_array_equal(first.points, second.points)

    def test_retained_points_are_measured_returns(self) -> None:
        """Voxel reduction keeps a real return, not a synthesized centroid."""
        chain = F.voxel_downsample(F.begin(self.cloud), 0.10)
        original = {tuple(point) for point in self.cloud}
        for point in chain.points:
            self.assertIn(tuple(point), original)

    def test_the_centroid_variant_does_synthesize_points(self) -> None:
        """It is offered, and it is honest about not being the default."""
        chain = F.voxel_centroid_downsample(F.begin(self.cloud), 0.10)
        original = {tuple(point) for point in self.cloud}
        synthesized = sum(
            1 for point in chain.points if tuple(point) not in original
        )
        self.assertGreater(synthesized, 0)


class OrderingTests(unittest.TestCase):
    """Downsampling concentrates outliers. Clean first."""

    def setUp(self) -> None:
        self.surface, self.clutter = _wall_with_clutter(n_surface=20000, n_clutter=400)
        self.cloud = np.vstack([self.surface, self.clutter])
        self.clutter_rows = {tuple(point) for point in self.clutter}

    def _clutter_fraction(self, points: np.ndarray) -> float:
        if not len(points):
            return 0.0
        hits = sum(1 for point in points if tuple(point) in self.clutter_rows)
        return hits / len(points)

    def test_downsampling_first_concentrates_the_noise(self) -> None:
        start = F.begin(self.cloud)
        before = self._clutter_fraction(start.points)
        after = self._clutter_fraction(F.voxel_downsample(start, 0.30).points)
        self.assertGreater(
            after,
            before * 5.0,
            "an isolated return survives as its own voxel while a dense "
            "surface is decimated, so the noise fraction rises",
        )

    def test_cleaning_first_leaves_a_cleaner_cloud(self) -> None:
        start = F.begin(self.cloud)
        wrong = F.density_outlier_removal(F.voxel_downsample(start, 0.30), 0.60, 2)
        right = F.voxel_downsample(F.density_outlier_removal(start, 0.15, 6), 0.30)
        self.assertLess(
            self._clutter_fraction(right.points),
            self._clutter_fraction(wrong.points),
        )

    def test_cleaning_after_downsampling_announces_that_it_cannot_work(self) -> None:
        chain = F.density_outlier_removal(
            F.voxel_downsample(F.begin(self.cloud), 0.30), 0.15, 6
        )
        advisory = chain.steps[-1].advisory
        self.assertIn("sparser than", advisory)
        self.assertIn("before downsampling", advisory)

    def test_cleaning_in_the_right_order_raises_no_advisory(self) -> None:
        chain = F.prepare_for_pose(self.cloud)
        self.assertEqual([s.advisory for s in chain.steps if s.advisory], [])

    def test_the_canonical_chains_share_one_source(self) -> None:
        pose = F.prepare_for_pose(self.cloud)
        measure = F.prepare_for_measurement(self.cloud)
        self.assertEqual(pose.source_digest, measure.source_digest)
        self.assertEqual(pose.source_digest, F.scan_digest(self.cloud))

    def test_pose_is_sparser_than_measurement(self) -> None:
        """Registration wants coverage; a face measurement wants density."""
        self.assertLess(
            F.prepare_for_pose(self.cloud).point_count,
            F.prepare_for_measurement(self.cloud).point_count,
        )


class OperationTests(unittest.TestCase):
    def setUp(self) -> None:
        surface, clutter = _wall_with_clutter()
        self.cloud = np.vstack([surface, clutter])

    def test_cropping_keeps_only_what_is_inside(self) -> None:
        chain = F.crop_to_bounds(F.begin(self.cloud), (0, -1, 0), (5, 1, 3))
        self.assertTrue(np.all(chain.points[:, 0] >= 0.0))
        self.assertTrue(np.all(chain.points[:, 0] <= 5.0))
        self.assertLess(chain.point_count, self.cloud.shape[0])

    def test_cropping_rejects_an_inverted_box(self) -> None:
        with self.assertRaises(ScanArtifactError):
            F.crop_to_bounds(F.begin(self.cloud), (5, 5, 5), (0, 0, 0))

    def test_a_range_gate_keeps_a_declared_standoff_band(self) -> None:
        chain = F.range_gate(F.begin(self.cloud), (0.0, 0.0, 0.0), 3.0, 0.5)
        distance = np.linalg.norm(chain.points, axis=1)
        self.assertTrue(np.all(distance >= 0.5))
        self.assertTrue(np.all(distance <= 3.0))

    def test_a_range_gate_rejects_an_inverted_band(self) -> None:
        with self.assertRaises(ScanArtifactError):
            F.range_gate(F.begin(self.cloud), (0.0, 0.0, 0.0), 1.0, 2.0)

    def test_density_removal_drops_isolated_returns(self) -> None:
        surface, clutter = _wall_with_clutter(n_surface=8000, n_clutter=300)
        cloud = np.vstack([surface, clutter])
        chain = F.density_outlier_removal(F.begin(cloud), 0.15, 6)
        kept = {tuple(p) for p in chain.points}
        survived = sum(1 for p in clutter if tuple(p) in kept)
        self.assertLess(survived, 0.5 * len(clutter))

    def test_the_neighbour_count_is_conservative(self) -> None:
        """Over-counting keeps points a strict radius search would drop."""
        # Two points 0.9 * radius apart are neighbours under any correct test.
        pair = np.array([[0.0, 0.0, 0.0], [0.09, 0.0, 0.0]])
        chain = F.density_outlier_removal(F.begin(pair), 0.10, 1)
        self.assertEqual(chain.point_count, 2)

    def test_bad_parameters_fail_loudly(self) -> None:
        start = F.begin(self.cloud)
        for call in (
            lambda: F.voxel_downsample(start, 0.0),
            lambda: F.voxel_downsample(start, -1.0),
            lambda: F.density_outlier_removal(start, float("nan"), 3),
            lambda: F.range_gate(start, (0, 0, 0), float("inf")),
        ):
            with self.subTest(call=call):
                with self.assertRaises(ScanArtifactError):
                    call()

    def test_a_malformed_cloud_is_refused(self) -> None:
        for bad in (np.zeros((4, 2)), np.array([[0.0, 0.0, np.nan]])):
            with self.subTest(shape=bad.shape):
                with self.assertRaises(ScanArtifactError):
                    F.begin(bad)

    def test_an_empty_cloud_survives_the_chain(self) -> None:
        empty = np.zeros((0, 3))
        chain = F.density_outlier_removal(F.voxel_downsample(F.begin(empty), 0.1), 0.1, 1)
        self.assertEqual(chain.point_count, 0)


class OwnershipTests(unittest.TestCase):
    """Filtering a capture must not confiscate it."""

    def test_the_callers_cloud_stays_writable(self) -> None:
        cloud = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]])
        chain = F.begin(cloud)
        cloud[0, 0] = 9.0  # the caller still owns this array
        self.assertEqual(chain.points[0, 0], 0.0, "and the copy did not follow")

    def test_the_filtered_points_are_frozen(self) -> None:
        chain = F.begin(np.zeros((4, 3)))
        with self.assertRaises(ValueError):
            chain.points[0, 0] = 1.0

    def test_a_scan_compares_and_hashes_by_its_digest(self) -> None:
        """A frozen dataclass over an ndarray cannot use the generated ones."""
        same = F.begin(np.zeros((4, 3))), F.begin(np.zeros((4, 3)))
        self.assertEqual(*same)
        self.assertEqual(len(set(same)), 1)
        self.assertNotEqual(same[0], F.begin(np.ones((4, 3))))

    def test_a_step_hashes_despite_holding_a_dict(self) -> None:
        step = F.FilterStep("m", {"a": 1.0, "b": 2.0}, 4, 2)
        self.assertEqual(hash(step), hash(F.FilterStep("m", {"b": 2.0, "a": 1.0}, 4, 2)))
        self.assertEqual(len({step, F.FilterStep("other", {}, 1, 1)}), 2)


class DeclaredCropTests(unittest.TestCase):
    """A crop that did not happen must not read as one nobody asked for."""

    def setUp(self) -> None:
        self.cloud = np.random.default_rng(3).uniform(0.0, 5.0, (600, 3))

    def test_neither_bound_declares_an_uncropped_capture(self) -> None:
        steps = [step.method for step in F.prepare_for_pose(self.cloud).steps]
        self.assertNotIn("crop_to_bounds", steps)

    def test_both_bounds_crop_and_record_it(self) -> None:
        chain = F.prepare_for_pose(self.cloud, (0.0, 0.0, 0.0), (5.0, 5.0, 5.0))
        self.assertIn("crop_to_bounds", [step.method for step in chain.steps])

    def test_one_bound_is_refused_rather_than_skipped(self) -> None:
        for kwargs in ({"lower": (0.0, 0.0, 0.0)}, {"upper": (5.0, 5.0, 5.0)}):
            for prepare in (F.prepare_for_pose, F.prepare_for_measurement):
                with self.subTest(bound=next(iter(kwargs)), prepare=prepare.__name__):
                    with self.assertRaisesRegex(ScanArtifactError, "needs both bounds"):
                        prepare(self.cloud, **kwargs)

if __name__ == "__main__":
    unittest.main()
