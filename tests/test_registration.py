"""Tests for gat/geometry/registration.py — scan-to-BIM GMM registration.

Uses a small synthetic scan (700 points, 1% cm sensor noise, 2% outliers,
seed 3) with a withheld ground-truth pose of yaw 20 deg and translation
(0.2, -0.1, 0.03), and asserts: pose recovery within 0.5 deg / 60 mm,
monotone NLL traces in both annealing stages, bitwise determinism of
register(), a symmetric positive-definite information matrix,
deterministic scan synthesis, and rejection of degenerate scans.
"""

from __future__ import annotations

from dataclasses import replace
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import gat.demo
from gat.errors import RegistrationError
from gat.geometry import registration
from gat.geometry.registration import (
    BASIN_TRANSLATION_TOL,
    BASIN_YAW_TOL,
    CONTENDER_WINDOW,
    RigidTransformZ,
    ScanRegistrar,
    _basin_separation,
    synthesize_scan,
)
from gat.geometry.stateio import derive_scene
from gat.session import GatSession

MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

TRUTH = RigidTransformZ(theta=math.radians(20.0), t=(0.2, -0.1, 0.03))

_CACHE: dict = {}


def _fixture() -> dict:
    """Shared expensive fixture, computed once per test process."""
    if not _CACHE:
        session = GatSession.load_ifc(MODEL)
        scene = derive_scene(session.world)
        scan = synthesize_scan(
            scene,
            n_points=700,
            noise_sigma=0.01,
            outlier_frac=0.02,
            transform=TRUTH,
            seed=3,
        )
        registrar = ScanRegistrar(scene)
        result = registrar.register(scan)
        result_again = registrar.register(scan)
        _CACHE.update(
            scene=scene,
            scan=scan,
            registrar=registrar,
            result=result,
            result_again=result_again,
        )
    return _CACHE


class RegistrationTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fx = _fixture()
        cls.scene = fx["scene"]
        cls.scan = fx["scan"]
        cls.registrar = fx["registrar"]
        cls.result = fx["result"]
        cls.result_again = fx["result_again"]


class TestRecovery(RegistrationTestBase):
    def test_pose_recovered(self):
        yaw_err, trans_err = self.result.transform.compose_error(TRUTH)
        self.assertLess(yaw_err, math.radians(0.5))
        self.assertLess(trans_err, 0.060)  # 60 mm

    def test_fit_accepted(self):
        self.assertTrue(self.result.accepted)

    def test_traces_monotone(self):
        for stage in (self.result.coarse_trace, self.result.nll_trace):
            diffs = np.diff(np.asarray(stage))
            self.assertTrue(
                (diffs <= 1e-9).all(),
                f"non-monotone stage trace: max increase {diffs.max()!r}",
            )

    def test_deterministic_register(self):
        a, b = self.result, self.result_again
        self.assertEqual(a.transform.theta, b.transform.theta)
        self.assertEqual(a.transform.t, b.transform.t)
        self.assertEqual(a.nll, b.nll)
        self.assertEqual(a.nll_trace, b.nll_trace)
        self.assertEqual(a.coarse_trace, b.coarse_trace)
        self.assertEqual(a.converged_nlls, b.converged_nlls)
        self.assertEqual(a.scan_digest, b.scan_digest)
        self.assertEqual(a.scene_version, b.scene_version)
        self.assertTrue(np.array_equal(a.info_matrix, b.info_matrix))


class TestInformationMatrix(RegistrationTestBase):
    def test_symmetric(self):
        H = self.result.info_matrix
        self.assertEqual(H.shape, (4, 4))
        self.assertLess(np.abs(H - H.T).max(), 1e-9 * max(1.0, np.abs(H).max()))

    def test_positive_definite(self):
        eigvals = np.linalg.eigvalsh(self.result.info_matrix)
        self.assertGreater(eigvals.min(), 0.0)

    def test_pose_sigma_finite_positive(self):
        sig = self.result.pose_sigma()
        self.assertTrue(np.isfinite(sig).all())
        self.assertTrue((sig > 0).all())


class TestSynthesizeScan(RegistrationTestBase):
    def test_deterministic_for_fixed_seed(self):
        again = synthesize_scan(
            self.scene,
            n_points=700,
            noise_sigma=0.01,
            outlier_frac=0.02,
            transform=TRUTH,
            seed=3,
        )
        self.assertTrue(np.array_equal(self.scan, again))

    def test_different_for_different_seeds(self):
        other = synthesize_scan(
            self.scene,
            n_points=700,
            noise_sigma=0.01,
            outlier_frac=0.02,
            transform=TRUTH,
            seed=4,
        )
        self.assertFalse(np.array_equal(self.scan, other))

    def test_point_count(self):
        self.assertEqual(self.scan.shape, (700, 3))


class TestDegenerateInput(RegistrationTestBase):
    def test_rejects_five_point_scan(self):
        rng = np.random.default_rng(0)
        tiny = rng.random((5, 3))
        with self.assertRaises(RegistrationError):
            self.registrar.register(tiny)

    def test_rejects_wrong_shape(self):
        with self.assertRaisesRegex(RegistrationError, "shape"):
            self.registrar.register(np.zeros((10, 2)))

    def test_rejects_non_finite_coordinates(self):
        bad = np.zeros((10, 3))
        bad[4, 1] = np.nan
        with self.assertRaisesRegex(RegistrationError, "non-finite"):
            self.registrar.register(bad)


class TestScanEvidence(RegistrationTestBase):
    def test_responsibility_mass_is_conserved_across_elements(self):
        report = self.registrar.evidence(self.scan, self.result)
        element_mass = sum(e.effective_points for e in report.elements)
        self.assertAlmostEqual(element_mass, report.inlier_effective_points, places=10)
        self.assertAlmostEqual(
            sum(e.responsibility_fraction for e in report.elements), 1.0, places=12
        )
        self.assertAlmostEqual(
            report.inlier_effective_points
            + report.outlier_fraction * report.point_count,
            report.point_count,
            places=10,
        )

    def test_metrics_are_bounded_and_finite(self):
        report = self.registrar.evidence(self.scan, self.result)
        solid_rows = {e.row for e in self.scene.elements if e.is_solid}
        self.assertEqual({e.element_row for e in report.elements}, solid_rows)
        self.assertGreater(report.inlier_effective_points, 0.0)
        self.assertGreaterEqual(report.outlier_fraction, 0.0)
        self.assertLessEqual(report.outlier_fraction, 1.0)
        for evidence in report.elements:
            self.assertGreater(evidence.primitive_count, 0)
            self.assertGreaterEqual(evidence.effective_points, 0.0)
            self.assertTrue(math.isfinite(evidence.mean_mahalanobis2))
            self.assertGreaterEqual(evidence.mean_mahalanobis2, 0.0)
            self.assertGreaterEqual(evidence.support_diversity, 0.0)
            self.assertLessEqual(evidence.support_diversity, 1.0 + 1e-12)
            self.assertGreaterEqual(evidence.assignment_confidence, 0.0)
            self.assertLessEqual(evidence.assignment_confidence, 1.0 + 1e-12)

    def test_report_is_deterministic_and_bound_to_provenance(self):
        first = self.registrar.evidence(self.scan, self.result)
        second = self.registrar.evidence(self.scan, self.result)
        self.assertEqual(first, second)
        self.assertEqual(first.scan_digest, self.result.scan_digest)
        self.assertEqual(first.scene_version, self.scene.version)

    def test_rejected_fit_produces_no_evidence(self):
        rejected = replace(self.result, accepted=False)
        with self.assertRaisesRegex(RegistrationError, "failed the fit gate"):
            self.registrar.evidence(self.scan, rejected)

    def test_different_scan_cannot_reuse_registration(self):
        different = self.scan.copy()
        different[0, 0] += 1e-12
        with self.assertRaisesRegex(RegistrationError, "differs"):
            self.registrar.evidence(different, self.result)

    def test_different_scene_version_cannot_reuse_registration(self):
        stale = replace(self.result, scene_version="not-this-scene")
        with self.assertRaisesRegex(RegistrationError, "different scene"):
            self.registrar.evidence(self.scan, stale)


class TestPlyHandoff(RegistrationTestBase):
    def test_register_ply_loads_vertices_then_delegates_to_same_gate(self):
        # The PLY adapter does not invent a second registration path.  It
        # decodes the producer artifact, then passes the same points and
        # caller-provided gates to ScanRegistrar.register().
        points = self.scan[:10]
        header = (
            "ply\nformat binary_little_endian 1.0\nelement vertex 10\n"
            "property float x\nproperty float y\nproperty float z\nend_header\n"
        ).encode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external_reconstruction.ply"
            path.write_bytes(header + np.asarray(points, dtype="<f4").tobytes())
            with patch.object(self.registrar, "register", return_value=self.result) as register:
                actual = self.registrar.register_ply(str(path), n_starts=4, accept_nll=2.5)

        self.assertIs(actual, self.result)
        register.assert_called_once()
        loaded, n_starts, accept_nll, basin_margin = register.call_args.args
        # The fixture deliberately serializes float32 PLY coordinates; the
        # loader promotes them to float64 without claiming lost source bits.
        np.testing.assert_allclose(loaded, points, rtol=0.0, atol=1e-6)
        self.assertEqual(n_starts, 4)
        self.assertEqual(accept_nll, 2.5)
        # A PLY goes through the same gates, basin separation included.
        self.assertEqual(basin_margin, 0.10)


class TestBasinSeparation(RegistrationTestBase):
    """A best fit is not an answer unless it is the only one.

    The starts are the only evidence this module has that the winner is
    unique, and until now their NLLs were recorded and discarded.
    """

    def test_a_full_scan_wins_its_basin_outright(self):
        self.assertTrue(self.result.accepted)
        self.assertEqual(self.result.refusal, "")
        self.assertGreaterEqual(self.result.basin_margin, 0.10)

    def test_each_reported_pose_is_reported_with_its_own_fit(self):
        self.assertEqual(
            len(self.result.converged_poses), len(self.result.converged_nlls)
        )

    def test_one_planar_wall_does_not_determine_where_it_was_scanned(self):
        """Two starts land 180 deg and 10.2 m apart, 6.5e-05 nats apart.

        Before the margin gated acceptance the registrar returned whichever
        of them came first and reported the fit as accepted.
        """
        rng = np.random.default_rng(4)
        n = 400
        wall = np.column_stack(
            [
                np.full(n, 5.1) + rng.normal(0.0, 0.002, n),
                rng.uniform(0.35, 3.65, n),
                np.full(n, 2.985) + rng.normal(0.0, 0.003, n),
            ]
        )
        result = self.registrar.register(wall)
        self.assertLess(result.nll, 6.0, "the fit itself is fine; that is the point")
        self.assertGreater(result.basin_count, 1)
        self.assertLess(result.basin_margin, 0.10)
        self.assertFalse(result.accepted)
        self.assertIn("does not determine where it was taken from", result.refusal)

    def test_agreeing_starts_are_one_basin_not_an_ambiguity(self):
        """Starts that converge to the same pose are agreement. Counting
        them as rivals would make every clean registration look ambiguous."""
        poses = [
            RigidTransformZ(0.10, (1.0, 2.0, 3.0)),
            RigidTransformZ(0.10 + 1e-9, (1.0, 2.0, 3.0 + 1e-9)),
            RigidTransformZ(0.10 + math.pi, (9.0, 2.0, 3.0)),
        ]
        count, margin = _basin_separation([1.0, 1.0 + 1e-12, 4.0], poses, 0)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(margin, 3.0)

    def test_unanimous_starts_are_unopposed_not_unmeasured(self):
        pose = RigidTransformZ(0.10, (1.0, 2.0, 3.0))
        count, margin = _basin_separation([1.0, 1.5], [pose, pose], 0)
        self.assertEqual(count, 1)
        self.assertEqual(margin, math.inf)

    def test_the_margin_is_a_declared_parameter(self):
        strict = self.registrar.register(self.scan, min_basin_margin=1e9)
        self.assertFalse(strict.accepted)
        self.assertIn("converged poses", strict.refusal)


class ConvergedBasinTests(RegistrationTestBase):
    """Basins are measured on converged poses, not on the starts.

    Six EM iterations from a 45-degree start barely moves: on the demo the
    eight coarse results sat within 2 degrees of the eight starts, so the gate
    was counting its own starts and reporting eight optima that did not exist.
    """

    def test_the_gate_clusters_fewer_poses_than_there_are_starts(self) -> None:
        self.assertLess(len(self.result.converged_poses), 8)
        self.assertEqual(len(self.result.converged_poses), len(self.result.converged_nlls))

    def test_no_reported_pose_is_another_one_counted_twice(self) -> None:
        """Contenders that reach the same optimum are one answer found twice.

        They are merged as they meet, so the reported set contains no two
        poses at the same point -- an invariant of the convergence, checked
        here on a real scan as well as argued in the module.
        """
        poses = self.result.converged_poses
        self.assertGreater(len(poses), 1, "a scan with one contender proves nothing")
        for index, pose in enumerate(poses):
            for other_index, other in enumerate(poses):
                if other_index <= index:
                    continue
                with self.subTest(pair=(index, other_index)):
                    yaw, translation = pose.compose_error(other)
                    self.assertFalse(
                        yaw <= BASIN_YAW_TOL / 10.0
                        and translation <= BASIN_TRANSLATION_TOL / 10.0,
                        "two reported poses are the same pose",
                    )

    def test_the_reported_poses_are_rivals_and_not_near_misses(self) -> None:
        """On this scan the survivors are separated by a quadrant and metres,
        so each is its own basin and the count is the number reported.

        A pair between the two tolerances -- merged by neither, grouped by
        basin clustering -- would make these two numbers disagree. That is
        allowed by construction and simply does not arise here."""
        poses = self.result.converged_poses
        self.assertEqual(self.result.basin_count, len(poses))
        for index, pose in enumerate(poses):
            for other in poses[index + 1:]:
                yaw, translation = pose.compose_error(other)
                self.assertGreater(yaw, BASIN_YAW_TOL)
                self.assertGreater(translation, BASIN_TRANSLATION_TOL)

    def test_a_clean_scan_separates_its_basins_decisively(self) -> None:
        """The demo building does have a 180-degree rival -- a rectangular
        plan is nearly symmetric -- and the converged margin to it is 0.47
        nats/point, comfortably above the 0.10 the gate asks for. The gate
        reported 8 basins and 0.27 before it clustered converged poses."""
        self.assertTrue(self.result.accepted)
        self.assertGreaterEqual(self.result.basin_count, 2)
        self.assertGreater(self.result.basin_margin, 4.0 * 0.10)

    def test_clustering_is_transitive(self) -> None:
        """A~B and B~C with A!~C is one basin, not two with a zero margin."""
        near = math.radians(4.0)
        chain = [
            RigidTransformZ(0.0, (0.0, 0.0, 0.0)),
            RigidTransformZ(near, (0.0, 0.0, 0.0)),
            RigidTransformZ(2 * near, (0.0, 0.0, 0.0)),
        ]
        count, margin = _basin_separation([1.0, 1.0, 1.0], chain, 0)
        self.assertEqual(count, 1)
        self.assertEqual(margin, math.inf)

        rival = RigidTransformZ(math.pi, (9.0, 0.0, 0.0))
        count, margin = _basin_separation([1.0, 1.0, 1.0, 4.0], chain + [rival], 0)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(margin, 3.0)


class SearchEconomyTests(RegistrationTestBase):
    """The pose search is cheap for two reasons, and both change what is
    searched. Neither may change what is *found*, so both are measured here
    against the exhaustive search they replace rather than argued for.

    Together they take this fixture from 59 s to 17 s. The demo goes from
    52 s to 30 s -- below where it sat before basin separation existed.
    """

    def test_a_pruned_start_could_never_have_been_the_rival(self) -> None:
        """Starts outside the contender window are dropped before convergence.

        That is only free if such a start could not have become the basin the
        margin is measured to. Converging all eight instead returns the same
        winning pose and the same margin to the last bit, and the four extra
        basins it finds sit 3.7 nats/point above the winner -- 37x the gate
        they would have to beat to matter.
        """
        with patch.object(registration, "CONTENDER_WINDOW", math.inf):
            exhaustive = self.registrar.register(self.scan)

        self.assertEqual(exhaustive.transform, self.result.transform)
        self.assertEqual(exhaustive.basin_margin, self.result.basin_margin)
        self.assertEqual(exhaustive.accepted, self.result.accepted)

        winner = min(exhaustive.converged_nlls)
        pruned = [n - winner for n in exhaustive.converged_nlls
                  if n - winner > CONTENDER_WINDOW]
        self.assertTrue(pruned, "nothing was pruned, so nothing was tested")
        self.assertEqual(
            len(exhaustive.converged_nlls) - len(pruned),
            len(self.result.converged_nlls),
            "the kept starts are exactly the ones inside the window",
        )
        self.assertGreater(min(pruned), 2.0)

    def test_the_probe_resolves_the_same_basins_as_every_point(self) -> None:
        """The search runs on a stride subsample; only the winner is refined
        on the full scan.

        Searching every point instead moves the final pose by 0.02 arcseconds
        and 0.4 nanometres -- the two answers are the same number -- and moves
        the margin by 0.035 nats/point, with both readings five times the gate.
        A subsample that could not resolve the structure would show up as a
        different basin count, so that is asserted too.
        """
        with patch.object(registration, "BASIN_SAMPLE_POINTS", 10 ** 9):
            dense = self.registrar.register(self.scan)

        yaw, translation = dense.transform.compose_error(self.result.transform)
        self.assertLess(math.degrees(yaw) * 3600.0, 1.0)   # arcseconds
        self.assertLess(translation, 1.0e-6)               # micrometres
        self.assertEqual(dense.basin_count, self.result.basin_count)
        self.assertEqual(dense.accepted, self.result.accepted)
        self.assertAlmostEqual(
            dense.basin_margin, self.result.basin_margin, delta=0.10
        )
        self.assertGreater(min(dense.basin_margin, self.result.basin_margin), 0.10)


if __name__ == "__main__":
    unittest.main()
