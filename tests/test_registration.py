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
    MAX_LIKELIHOOD_BYTES,
    MAX_TRANSLATION_SIGMA,
    MAX_YAW_SIGMA,
    _marginal_sigma,
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
        (
            loaded,
            n_starts,
            accept_nll,
            basin_margin,
            yaw_sigma,
            translation_sigma,
        ) = register.call_args.args
        # The fixture deliberately serializes float32 PLY coordinates; the
        # loader promotes them to float64 without claiming lost source bits.
        np.testing.assert_allclose(loaded, points, rtol=0.0, atol=1e-6)
        self.assertEqual(n_starts, 4)
        self.assertEqual(accept_nll, 2.5)
        # A PLY goes through every gate the native path does, at the same
        # defaults -- basin separation and pose uncertainty included. A gate
        # added to register() and not threaded through here would be a hole
        # under whatever a reconstruction engine hands over.
        self.assertEqual(basin_margin, 0.10)
        self.assertEqual(yaw_sigma, MAX_YAW_SIGMA)
        self.assertEqual(translation_sigma, MAX_TRANSLATION_SIGMA)


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


class PoseUncertaintyGateTests(RegistrationTestBase):
    """A fit can clear both per-point gates and still not place the scan.

    ``nll`` and ``basin_margin`` are both means over points. A dozen returns
    can separate two basins by 2.2 nats/point and fit them well, and still
    leave the pose a degree and a metre out -- there are simply not enough of
    them for either number to mean what it says. The information matrix is
    the one quantity here that counts evidence rather than averaging it, and
    until now it was computed, reported, and never asked.
    """

    #: The same demo building, scanned too sparsely to place. Both are
    #: accepted by the fit and the margin; both have the pose badly wrong.
    SPARSE = ((10, 5, 10.9, 0.865), (20, 5, 2.1, 0.279))

    def _sparse(self, n_points: int, seed: int) -> np.ndarray:
        return synthesize_scan(
            self.scene, n_points=n_points, noise_sigma=0.01,
            outlier_frac=0.02, transform=TRUTH, seed=seed,
        )

    def test_a_scan_too_sparse_to_place_is_refused(self) -> None:
        for n_points, seed, yaw_deg, translation_m in self.SPARSE:
            with self.subTest(n_points=n_points):
                scan = self._sparse(n_points, seed)
                result = self.registrar.register(scan)

                yaw, translation = result.transform.compose_error(TRUTH)
                self.assertAlmostEqual(math.degrees(yaw), yaw_deg, delta=0.5)
                self.assertAlmostEqual(translation, translation_m, delta=0.05)

                self.assertFalse(result.accepted)
                self.assertIn("uncertain to at least", result.refusal)

    def test_the_other_two_gates_would_have_accepted_it(self) -> None:
        """The point of the gate: without it these scans pass everything.

        Both clear the fit and clear the margin -- one of them by 2.2
        nats/point, four times what the 4000-point capture manages -- so
        neither existing gate is what refuses them.
        """
        for n_points, seed, _, _ in self.SPARSE:
            with self.subTest(n_points=n_points):
                scan = self._sparse(n_points, seed)
                result = self.registrar.register(
                    scan, max_yaw_sigma=math.inf, max_translation_sigma=math.inf
                )
                self.assertTrue(
                    result.accepted,
                    "these scans are refused by the uncertainty gate alone; if "
                    "another gate now catches them this test proves nothing",
                )
                self.assertLess(result.nll, 6.0)
                self.assertGreaterEqual(result.basin_margin, 0.10)

    def test_the_limits_are_declared_parameters(self) -> None:
        scan = self._sparse(*self.SPARSE[0][:2])
        self.assertFalse(self.registrar.register(scan).accepted)
        self.assertTrue(
            self.registrar.register(
                scan, max_yaw_sigma=math.inf, max_translation_sigma=math.inf
            ).accepted
        )

    def test_a_scan_dense_enough_to_place_still_passes(self) -> None:
        """The gate must cost nothing on the captures it is meant to admit."""
        self.assertTrue(self.result.accepted)
        self.assertEqual(self.result.refusal, "")
        yaw_sigma, *translation_sigma = self.result.pose_sigma()
        self.assertLess(yaw_sigma, MAX_YAW_SIGMA / 5.0)
        self.assertLess(max(translation_sigma), MAX_TRANSLATION_SIGMA / 5.0)

    def test_the_gate_cannot_see_a_rival_basin(self) -> None:
        """Why this gate is added to the margin rather than replacing it.

        The information matrix is local curvature at one optimum. On the
        single wall -- two poses a quadrant and ten metres apart, 6.5e-05
        nats between them -- it reports a comfortable fraction of a degree,
        because each optimum on its own is sharp. Only the margin sees that
        there are two of them.
        """
        rng = np.random.default_rng(4)
        n = 400
        wall = np.column_stack([
            np.full(n, 5.1) + rng.normal(0.0, 0.002, n),
            rng.uniform(0.35, 3.65, n),
            np.full(n, 2.985) + rng.normal(0.0, 0.003, n),
        ])
        result = self.registrar.register(wall)
        self.assertLess(result.pose_sigma()[0], MAX_YAW_SIGMA)
        self.assertFalse(result.accepted)
        self.assertIn("does not determine where it was taken from", result.refusal)


class MarginalSigmaTests(unittest.TestCase):
    """An information matrix that determines nothing must not report certainty."""

    def test_a_healthy_matrix_inverts_normally(self) -> None:
        sigma = _marginal_sigma(np.diag([4.0, 100.0, 100.0, 100.0]))
        self.assertAlmostEqual(sigma[0], 0.5)
        self.assertAlmostEqual(sigma[1], 0.1)

    def test_a_singular_matrix_is_infinitely_uncertain(self) -> None:
        sigma = _marginal_sigma(np.zeros((4, 4)))
        self.assertTrue(np.all(np.isinf(sigma)))

    def test_a_negative_variance_is_not_clipped_to_certainty(self) -> None:
        """Clipping is the dangerous reading: it turns a broken inverse into
        a pose known exactly, and every threshold downstream then passes."""
        sigma = _marginal_sigma(np.diag([1.0, -1.0, 1.0, 1.0]))
        self.assertEqual(sigma[1], math.inf)
        self.assertAlmostEqual(sigma[0], 1.0)

    def test_a_non_finite_matrix_is_infinitely_uncertain(self) -> None:
        for bad in (np.nan, np.inf):
            with self.subTest(value=bad):
                H = np.eye(4)
                H[2, 2] = bad
                self.assertTrue(np.all(np.isinf(_marginal_sigma(H))))


class StartCountTests(RegistrationTestBase):
    """The starts are the only evidence that the winner is unique."""

    def test_a_single_start_cannot_witness_uniqueness(self) -> None:
        """One start yields one basin, and one basin reports an infinite
        margin -- 'unopposed', which is the correct reading for eight starts
        that agree and exactly the wrong one for a start with no opponent."""
        with self.assertRaises(RegistrationError) as caught:
            self.registrar.register(self.scan, n_starts=1)
        self.assertIn("unique", str(caught.exception))

    def test_no_starts_is_a_refusal_not_an_internal_error(self) -> None:
        with self.assertRaises(RegistrationError):
            self.registrar.register(self.scan, n_starts=0)

    def test_two_starts_are_enough_to_be_asked(self) -> None:
        result = self.registrar.register(self.scan, n_starts=2)
        self.assertEqual(result.basin_count, 2)
        self.assertEqual(result.basin_margin, self.result.basin_margin)


class CapacityTests(RegistrationTestBase):
    """A scene this estimator cannot serve is refused, not attempted.

    ``_log_components`` forms an (M, K, 3) difference between every point and
    every primitive. Measured on the shipped model and multiples of it, a full
    ``register`` of a 2000-point scan costs 11.6 s at K=190 and 173 s at
    K=3040 -- linear in K, about 1.35 s per hundred primitives -- so a
    thousand-element storey is some twenty minutes and ten thousand needs a
    3.4 GB intermediate at the probe size alone.

    Ungated that arrives as a swap-thrash or an OOM kill. On Linux the
    allocation usually succeeds and the process dies later writing to it, so
    there is no exception to catch: checking before allocating is the only
    place a refusal can still be made.
    """

    def test_an_oversized_evaluation_is_refused_by_name(self) -> None:
        tight = ScanRegistrar(self.scene, max_likelihood_bytes=1024)
        with self.assertRaises(RegistrationError) as caught:
            tight.register(self.scan)
        message = str(caught.exception)
        self.assertIn("too large for this estimator", message)
        self.assertIn("primitives", message)
        # The remedies, so the refusal is actionable rather than only true.
        self.assertIn("scan_filter", message)
        self.assertIn("max_likelihood_bytes", message)

    def test_the_refusal_states_a_size_a_reader_can_hold(self) -> None:
        """A byte count rendered only in GiB reads '0.0 GiB' for every limit
        below a gigabyte, which is the range a caller most likely set."""
        tight = ScanRegistrar(self.scene, max_likelihood_bytes=1024)
        with self.assertRaises(RegistrationError) as caught:
            tight.register(self.scan)
        self.assertNotIn("0.0 GiB", str(caught.exception))
        self.assertIn("1.0 KiB", str(caught.exception))

    def test_the_check_runs_before_the_allocation(self) -> None:
        """A gate that fires after the array exists has not prevented
        anything. Refuse a size numpy could never allocate and the error has
        to be this one, not MemoryError."""
        huge = ScanRegistrar(self.scene)
        # A broadcast view: the right shape, no allocation. Building the real
        # array to test the guard would hit the very failure it prevents --
        # this test asked numpy for 44.7 GiB on its first attempt.
        huge.means = np.broadcast_to(np.zeros(3), (2 * 10**9, 3))
        with self.assertRaises(RegistrationError) as caught:
            huge.nll(self.scan, self.result.transform)
        self.assertIn("too large for this estimator", str(caught.exception))

    def test_the_shipped_model_is_nowhere_near_the_limit(self) -> None:
        """The gate is a backstop, not a budget: it must never fire on work
        this runtime is meant to do."""
        needed = (
            self.scan.shape[0] * self.registrar.means.shape[0]
            * 3 * np.dtype(np.float64).itemsize
        )
        self.assertLess(needed * 100, MAX_LIKELIHOOD_BYTES)
        self.assertTrue(self.result.accepted)


class DeclaredParameterTests(RegistrationTestBase):
    """Every knob on this instrument is refused when it is not a setting.

    Found by handing each parameter the values a caller mistypes. Most of
    the gates turned out to be fail-closed already -- nan and negative
    thresholds make them refuse everything, which is the safe direction --
    but four settings were read as something other than what was passed,
    and one switched a gate off.
    """

    def test_a_negative_smoothing_scale_is_not_its_own_magnitude(self) -> None:
        """``reg_sigma`` is used only as ``reg_sigma**2``, so -0.08 built an
        instrument identical to +0.08 and -1.0 one identical to +1.0, with no
        complaint. A sign error silently changed which instrument answered."""
        for name in ("reg_sigma", "fine_sigma"):
            for value in (-0.08, -1.0, 0.0, math.nan, math.inf):
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(RegistrationError) as caught:
                        ScanRegistrar(self.scene, **{name: value})
                    self.assertIn(name, str(caught.exception))

    def test_a_mixture_weight_outside_the_unit_interval_is_refused(self) -> None:
        """0, 1 and negatives reached ``math.log`` and came back as
        'ValueError: math domain error', naming neither the parameter nor
        the mistake."""
        for value in (0.0, 1.0, -0.5, 1.5, math.nan):
            with self.subTest(outlier_pi=value):
                with self.assertRaises(RegistrationError) as caught:
                    ScanRegistrar(self.scene, outlier_pi=value)
                self.assertIn("outlier_pi", str(caught.exception))

    def test_an_iteration_budget_of_zero_is_refused(self) -> None:
        """``max_iter=0`` ran no EM at all and returned the centroid-matched
        start -- 1.5 m from truth -- as a registration. It was refused only
        because that pose happened to fit badly."""
        for value in (0, -3):
            with self.subTest(max_iter=value):
                with self.assertRaises(RegistrationError):
                    ScanRegistrar(self.scene, max_iter=value)

    def test_a_gate_threshold_that_could_never_refuse_is_refused(self) -> None:
        """``basin_margin`` is non-negative by construction, so any negative
        threshold switches the ambiguity gate off. It was the one gate
        parameter that failed open on a bad value."""
        with self.assertRaises(RegistrationError) as caught:
            self.registrar.register(self.scan, min_basin_margin=-1.0)
        self.assertIn("could never refuse", str(caught.exception))

    def test_nan_thresholds_are_refused_rather_than_silently_refusing(self) -> None:
        """A nan threshold makes every comparison false, so the gate refuses
        everything -- safe, but the refusal then quotes a limit of nan and
        the caller learns nothing about what they passed."""
        for name in ("accept_nll", "min_basin_margin", "max_yaw_sigma",
                     "max_translation_sigma"):
            with self.subTest(parameter=name):
                with self.assertRaises(RegistrationError) as caught:
                    self.registrar.register(self.scan, **{name: math.nan})
                self.assertIn(name, str(caught.exception))

    def test_infinity_still_stands_a_gate_down_deliberately(self) -> None:
        """The validation must not take away the documented way to disable a
        gate for a measurement, which the search-economy tests rely on."""
        loose = self.registrar.register(
            self.scan, max_yaw_sigma=math.inf, max_translation_sigma=math.inf
        )
        self.assertTrue(loose.accepted)

    def test_a_non_integer_start_count_is_refused(self) -> None:
        with self.assertRaises(RegistrationError):
            self.registrar.register(self.scan, n_starts=2.5)

    def test_a_scan_that_is_not_numbers_is_refused_by_name(self) -> None:
        """An object array reached numpy as 'could not convert string to
        float', which does not say it was the scan."""
        with self.assertRaises(RegistrationError) as caught:
            self.registrar.register(np.array([["a", "b", "c"]] * 20, dtype=object))
        self.assertIn("scan", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
