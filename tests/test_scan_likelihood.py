"""Tests for calibrated scan-to-clearance likelihood adaptation."""

from __future__ import annotations

from dataclasses import replace
import math
import os
import unittest

import numpy as np

import gat.demo
from gat.engine.decision import DecisionVerdict
from gat.engine.executor import execute
from gat.engine.stability import analyze
from gat.engine.transform import ShiftParameter
from gat.errors import BindingError, LikelihoodCalibrationError
from gat.geometry import (
    ClearanceDecision,
    ClearanceLikelihoodCalibration,
    IndependentPoseCalibration,
    OrientedBox,
    RegistrationResult,
    RigidTransformZ,
    ScanRegistrar,
    adapt_clearance_likelihood,
    assess_clearance,
    derive_scene,
    plan_clearance_evidence,
)
from gat.geometry.scan_likelihood import _on_support_face, _settle_support_window
from gat.geometry.stateio import rot_z, support_radius
from gat.geometry.registration import (
    ElementScanEvidence,
    ScanEvidenceReport,
    _scan_digest,
)
from gat.session import GatSession
from gat.workflows import (
    AcceptanceCase,
    AcceptanceDisposition,
    EvidenceReceipt,
    WorkflowKind,
    clearance_check,
    evaluate_acceptance_case,
)


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


class ScanLikelihoodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(MODEL)
        cls.scene = derive_scene(cls.session.world)
        cls.registrar = ScanRegistrar(cls.scene)

        rng = np.random.default_rng(4)
        count = 180
        # Independent survey points on the Wall-Party top face, whose true
        # support is 15 mm below the current BIM mean.
        cls.scan = np.column_stack(
            [
                np.full(count, 5.1) + rng.normal(0.0, 0.002, count),
                rng.uniform(0.35, 3.65, count),
                np.full(count, 2.985) + rng.normal(0.0, 0.003, count),
            ]
        )
        cls.scan_digest = _scan_digest(cls.scan)
        cls.registration = RegistrationResult(
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.0)),
            nll=0.0,
            nll_trace=(),
            coarse_trace=(),
            converged_nlls=(),
            info_matrix=np.diag([1.0e4] * 4),
            accepted=True,
            scan_digest=cls.scan_digest,
            scene_version=cls.scene.version,
        )
        party = cls.scene.element_by_name("Wall-Party")
        cls.evidence = ScanEvidenceReport(
            scan_digest=cls.scan_digest,
            scene_version=cls.scene.version,
            point_count=count,
            inlier_effective_points=170.0,
            outlier_fraction=0.01,
            elements=(
                ElementScanEvidence(
                    element_row=party.row,
                    element_name=party.name,
                    primitive_count=20,
                    effective_points=170.0,
                    responsibility_fraction=1.0,
                    mean_mahalanobis2=2.0,
                    support_diversity=0.80,
                    assignment_confidence=0.98,
                ),
            ),
        )
        cls.assessment = assess_clearance(
            cls.scene,
            ClearanceDecision(
                proposed=OrientedBox(
                    (4.0, 1.8, 3.06), 0.0, (3.0, 0.4, 0.4)
                ),
                required_clearance=0.05,
                confidence=0.95,
                position_sigma=0.002,
                label="survey-conditioned route",
            ),
        )
        cls.plan = plan_clearance_evidence(cls.assessment, cls.evidence)
        cls.pose = IndependentPoseCalibration(
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.0)),
            covariance=np.diag([1.0e-8, 1.0e-6, 1.0e-6, 1.0e-6]),
            scan_digest=cls.scan_digest,
            source_id="survey-control-A",
        )

    def likelihood(self, **kwargs):
        return adapt_clearance_likelihood(
            self.scene,
            self.registrar,
            self.scan,
            kwargs.pop("registration", self.registration),
            kwargs.pop("evidence", self.evidence),
            kwargs.pop("plan", self.plan),
            kwargs.pop("pose", self.pose),
            kwargs.pop("calibration", ClearanceLikelihoodCalibration()),
            **kwargs,
        )

    def test_extracts_controlling_support_face_not_centroid(self) -> None:
        likelihood = self.likelihood()
        self.assertEqual(likelihood.element_name, "Wall-Party")
        self.assertEqual(likelihood.direction, (0.0, 0.0, 1.0))
        self.assertAlmostEqual(likelihood.predicted_support, 3.0, delta=1e-12)
        self.assertAlmostEqual(likelihood.observed_support, 2.985, delta=0.002)
        self.assertGreater(likelihood.effective_face_points, 150.0)
        self.assertGreater(likelihood.face_assignment_confidence, 0.99)
        self.assertGreater(likelihood.tangent_rms, 0.5)

    def test_uncertainty_budget_includes_all_three_sources(self) -> None:
        likelihood = self.likelihood()
        self.assertGreater(likelihood.sampling_sigma, 0.0)
        self.assertGreater(likelihood.pose_sigma, 0.0)
        self.assertGreater(likelihood.calibration_sigma, 0.0)
        expected = np.sqrt(
            likelihood.sampling_sigma**2
            + likelihood.pose_sigma**2
            + likelihood.calibration_sigma**2
        )
        self.assertAlmostEqual(likelihood.noise_sigma, expected, delta=1e-15)

    def test_condition_propagate_verify_closes_clearance_decision(self) -> None:
        self.assertEqual(self.assessment.verdict, DecisionVerdict.UNRESOLVED)
        likelihood = self.likelihood()
        clear_height = likelihood.observation.target_vars()[0]
        prior_sigma = self.scene.world.belief.std(clear_height)

        result = execute(self.scene.world, likelihood.observation)

        self.assertTrue(result.committed)
        self.assertTrue(result.report.passed)
        self.assertLess(result.world.belief.std(clear_height), prior_sigma)
        updated_scene = derive_scene(result.world)
        resolved = assess_clearance(updated_scene, self.assessment.decision)
        self.assertEqual(resolved.verdict, DecisionVerdict.SATISFIED)
        self.assertLessEqual(resolved.p_any_violation_upper, 0.05)

    def test_linearized_observation_is_rejected_after_prior_changes(self) -> None:
        likelihood = self.likelihood()
        target = likelihood.observation.target_vars()[0]
        changed = execute(
            self.scene.world, ShiftParameter(target, 0.001)
        ).world
        with self.assertRaisesRegex(BindingError, "stale"):
            execute(changed, likelihood.observation)

    def test_observation_participates_in_stability_analysis(self) -> None:
        report = analyze(self.scene.world, [self.likelihood().observation])
        self.assertLess(report.energy_trace[-1], report.energy_trace[0])
        self.assertLess(report.sigma_min, 1.0)

    def test_pose_uncertainty_increases_likelihood_noise(self) -> None:
        baseline = self.likelihood()
        noisier_pose = replace(
            self.pose,
            covariance=np.diag([1.0e-8, 1.0e-6, 1.0e-6, 9.0e-6]),
            source_id="survey-control-B",
        )
        noisier = self.likelihood(pose=noisier_pose)
        self.assertGreater(noisier.pose_sigma, baseline.pose_sigma)
        self.assertGreater(noisier.noise_sigma, baseline.noise_sigma)

    def test_pose_disagreement_is_rejected(self) -> None:
        mismatched = replace(
            self.pose,
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.10)),
        )
        with self.assertRaisesRegex(LikelihoodCalibrationError, "disagrees"):
            self.likelihood(pose=mismatched)

    def test_scan_provenance_mismatch_is_rejected(self) -> None:
        mismatched = replace(self.pose, scan_digest="other-scan")
        with self.assertRaisesRegex(LikelihoodCalibrationError, "digests differ"):
            self.likelihood(pose=mismatched)

    def test_low_quality_element_evidence_is_rejected(self) -> None:
        weak_row = replace(self.evidence.elements[0], effective_points=4.0)
        weak = replace(self.evidence, elements=(weak_row,))
        with self.assertRaisesRegex(LikelihoodCalibrationError, "effective points"):
            self.likelihood(evidence=weak)

    def test_face_coverage_and_innovation_gates_are_enforced(self) -> None:
        with self.assertRaisesRegex(LikelihoodCalibrationError, "support face"):
            self.likelihood(
                calibration=replace(
                    ClearanceLikelihoodCalibration(),
                    min_face_effective_points=1000.0,
                )
            )
        with self.assertRaisesRegex(LikelihoodCalibrationError, "innovation gate"):
            self.likelihood(
                calibration=replace(
                    ClearanceLikelihoodCalibration(), max_innovation_sigma=1.0
                )
            )

    # -- gates on quantities that were measured and then ignored -----------

    def _scan_like(self, ys, zs):
        """Another survey of the same face, so only the sampling differs."""
        rng = np.random.default_rng(11)
        n = len(ys)
        return np.column_stack(
            [np.full(n, 5.1) + rng.normal(0.0, 0.002, n), ys, zs]
        )

    def _likelihood_for(self, scan, **calibration):
        digest = _scan_digest(scan)
        return adapt_clearance_likelihood(
            self.scene,
            self.registrar,
            scan,
            replace(self.registration, scan_digest=digest),
            replace(self.evidence, scan_digest=digest, point_count=len(scan)),
            replace(self.plan, scan_digest=digest),
            replace(self.pose, scan_digest=digest),
            replace(ClearanceLikelihoodCalibration(), **calibration),
        )

    def test_two_clusters_at_the_ends_do_not_cover_a_face(self) -> None:
        """The case min_tangent_rms rewards: it measures spread, and spread
        is exactly what putting every return at the two extremes maximizes."""
        rng = np.random.default_rng(7)
        n = 180
        ys = np.concatenate(
            [rng.normal(0.40, 0.004, n // 2), rng.normal(3.60, 0.004, n // 2)]
        )
        zs = np.full(n, 2.985) + rng.normal(0.0, 0.003, n)
        clustered = self._scan_like(ys, zs)

        spread = self._likelihood_for(self._scan_like(rng.uniform(0.35, 3.65, n), zs))
        with self.assertRaisesRegex(LikelihoodCalibrationError, "do not sample it"):
            self._likelihood_for(clustered)

        # With the coverage gate stood down, the clustered scan passes the
        # gate that was supposed to catch it -- and scores *better* on it.
        waved_through = self._likelihood_for(clustered, min_face_coverage=0.01)
        self.assertGreater(waved_through.tangent_rms, spread.tangent_rms)
        self.assertLess(waved_through.face_coverage, spread.face_coverage)

    def test_a_bulged_face_has_no_support_plane(self) -> None:
        """45 mm of structure over a third of the face used to widen sigma by
        0.2 mm, because the residual is divided by the return count."""
        rng = np.random.default_rng(7)
        n = 180
        ys = rng.uniform(0.35, 3.65, n)
        zs = np.full(n, 2.985) + rng.normal(0.0, 0.003, n)
        flat = self._likelihood_for(self._scan_like(ys, zs))

        bulged = zs.copy()
        bulged[ys > 2.8] += 0.045
        with self.assertRaisesRegex(LikelihoodCalibrationError, "shape, not noise"):
            self._likelihood_for(self._scan_like(ys, bulged))

        self.assertLess(flat.face_residual_rms, 0.010)
        self.assertGreater(flat.face_coverage, 0.15)

    def test_a_refused_registration_cannot_place_a_measurement(self) -> None:
        """`accepted` is documented as the gate for any write-back, and
        nothing downstream read it."""
        with self.assertRaisesRegex(
            LikelihoodCalibrationError, "registration was not accepted"
        ):
            self.likelihood(
                registration=replace(
                    self.registration, accepted=False, refusal="basins tied"
                )
            )

    def test_adaptation_is_deterministic_and_does_not_mutate_world(self) -> None:
        digest_before = self.scene.world.digest()
        first = self.likelihood()
        second = self.likelihood()
        self.assertEqual(self.scene.world.digest(), digest_before)
        self.assertEqual(first.evidence_digest, second.evidence_digest)
        self.assertEqual(first.observed_support, second.observed_support)
        self.assertTrue(
            np.array_equal(first.observation.row, second.observation.row)
        )

    def test_verified_scan_transition_can_close_an_as_built_acceptance_case(self) -> None:
        likelihood = self.likelihood()
        session = GatSession(self.scene.world)
        result = session.run(
            likelihood.observation,
            provenance={
                "evidence_kind": "calibrated-scan-clearance-likelihood",
                "calibration_id": likelihood.pose_source_id,
                "scan_digest": likelihood.scan_digest,
                "check_ids": ["route-clearance"],
            },
        )
        receipt = EvidenceReceipt.from_scan_likelihood(
            likelihood,
            result,
            session.ledger.events[-1],
            ("route-clearance",),
        )
        posterior = assess_clearance(
            derive_scene(session.world), self.assessment.decision
        )
        case = AcceptanceCase(
            "as-built-route-1",
            WorkflowKind.AS_BUILT_CLEARANCE,
            "survey-conditioned route",
            (clearance_check("route-clearance", posterior),),
        )
        outcome = evaluate_acceptance_case(case, (receipt,))

        self.assertEqual(posterior.verdict, DecisionVerdict.SATISFIED)
        self.assertEqual(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertTrue(outcome.may_authorize)
        self.assertEqual(outcome.evidence_receipt_ids, (receipt.receipt_id,))


class SupportWindowFollowsTheReturnsTests(unittest.TestCase):
    """The support window used to sit on the BIM's own answer and never move.

    ``face_mask`` was ``|projections - predicted| <= face_band`` with
    ``predicted`` the model's prediction of where the face is. A face at
    ``predicted + delta`` is then one-side truncated by that window, so the
    reported ``observed_support`` is pulled back toward the model. Measured
    through this whole pipeline on Wall-Party's top face, 400 returns at a
    10 mm sensor:

        true offset   reported   shortfall   residual rms   outcome
           30 mm       29.4 mm     0.6 mm      10.00 mm     reported
           40 mm       38.8 mm     1.2 mm       9.40 mm     reported
           50 mm       46.7 mm     3.3 mm       7.98 mm     reported
           55 mm       49.9 mm     5.1 mm       7.17 mm     reported
           60 mm       52.0 mm     8.0 mm       6.45 mm     reported
           70 mm       53.9 mm    16.1 mm       4.67 mm     reported
           80 mm         --          --           --        refused

    Three things wrong at once. The reported deviation is short, and short
    in the direction of agreeing with the model. ``face_residual_rms``, taken
    about that already-pulled mean, *falls* as the deviation grows -- the
    gate meant to catch "this is a shape, not noise" reads 4.67 mm against
    its 15 mm bound at the point of worst error, quieter than it reads on a
    face that is exactly right. And the shrunken deviation is a shrunken
    innovation, so the 5-sigma innovation gate does not see it either.

    Beyond 80 mm the element's own GMM responsibilities die and the case
    refuses on effective points; that part always worked. The hole is the
    band either side of it, where a real as-built deviation is reported as a
    smaller one with every gate green.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(MODEL)
        cls.scene = derive_scene(cls.session.world)
        cls.registrar = ScanRegistrar(cls.scene)
        cls.party = cls.scene.element_by_name("Wall-Party")

    def _harness(self, z_values: np.ndarray):
        """Everything ``adapt_clearance_likelihood`` needs, for one scan."""
        count = int(z_values.shape[0])
        rng = np.random.default_rng(4)
        scan = np.column_stack(
            [
                np.full(count, 5.1) + rng.normal(0.0, 0.002, count),
                rng.uniform(0.35, 3.65, count),
                z_values,
            ]
        )
        digest = _scan_digest(scan)
        registration = RegistrationResult(
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.0)),
            nll=0.0,
            nll_trace=(),
            coarse_trace=(),
            converged_nlls=(),
            info_matrix=np.diag([1.0e4] * 4),
            accepted=True,
            scan_digest=digest,
            scene_version=self.scene.version,
        )
        evidence = ScanEvidenceReport(
            scan_digest=digest,
            scene_version=self.scene.version,
            point_count=count,
            inlier_effective_points=float(count) * 0.94,
            outlier_fraction=0.01,
            elements=(
                ElementScanEvidence(
                    element_row=self.party.row,
                    element_name=self.party.name,
                    primitive_count=20,
                    effective_points=float(count) * 0.94,
                    responsibility_fraction=1.0,
                    mean_mahalanobis2=2.0,
                    support_diversity=0.80,
                    assignment_confidence=0.98,
                ),
            ),
        )
        assessment = assess_clearance(
            self.scene,
            ClearanceDecision(
                proposed=OrientedBox((4.0, 1.8, 3.06), 0.0, (3.0, 0.4, 0.4)),
                required_clearance=0.05,
                confidence=0.95,
                position_sigma=0.002,
                label="survey-conditioned route",
            ),
        )
        pose = IndependentPoseCalibration(
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.0)),
            covariance=np.diag([1.0e-8, 1.0e-6, 1.0e-6, 1.0e-6]),
            scan_digest=digest,
            source_id="survey-control-A",
        )
        return (scan, registration, evidence, plan_clearance_evidence(assessment, evidence), pose)

    def _at_offset(self, delta: float, count: int = 400, sigma: float = 0.010):
        """A flat face on Wall-Party's top, ``delta`` metres off the model."""
        rng = np.random.default_rng(17)
        return self._harness(
            np.full(count, 3.0 + delta) + rng.normal(0.0, sigma, count)
        )

    def _run(self, harness, calibration=None):
        scan, registration, evidence, plan, pose = harness
        return adapt_clearance_likelihood(
            self.scene,
            self.registrar,
            scan,
            registration,
            evidence,
            plan,
            pose,
            calibration or ClearanceLikelihoodCalibration(),
        )

    #: What the pipeline reads on a face that is exactly where the model puts
    #: it. Not zero: the returns are weighted by responsibilities that are
    #: themselves centred on the model, which costs a constant half
    #: millimetre. Constant is the point -- it is the same at 0 mm as at
    #: 55 mm, so it is not the truncation this class is about.
    BASELINE_SHORTFALL = 0.0005

    def test_a_face_where_the_model_says_reads_where_the_model_says(self) -> None:
        likelihood = self._run(self._at_offset(0.0))
        self.assertAlmostEqual(likelihood.predicted_support, 3.0, delta=1e-12)
        self.assertAlmostEqual(likelihood.observed_support, 3.0, delta=0.002)

    def test_a_deviated_face_reads_where_it_actually_is(self) -> None:
        """The whole point. Pinned, a 55 mm offset read 49.9 mm; the error
        grew with the offset, which is the worst shape an error can have in
        an instrument whose output *is* the deviation."""
        for delta_mm in (5, 15, 25, 35, 45, 50, 55):
            with self.subTest(offset_mm=delta_mm):
                delta = delta_mm / 1000.0
                likelihood = self._run(self._at_offset(delta))
                observed = likelihood.observed_support - likelihood.predicted_support
                self.assertAlmostEqual(observed, delta, delta=0.0015)

    def test_the_shortfall_no_longer_grows_with_the_deviation(self) -> None:
        """Pinned: 0.5, 0.6, 1.2, 3.3, 5.1 mm short at 20/30/40/50/55 mm.
        Settled it must be flat -- whatever residual bias remains must not
        be a function of how wrong the model is."""
        shortfalls = []
        for delta_mm in (0, 20, 30, 40, 50, 55):
            likelihood = self._run(self._at_offset(delta_mm / 1000.0))
            observed = likelihood.observed_support - likelihood.predicted_support
            shortfalls.append(delta_mm / 1000.0 - observed)
        for value in shortfalls:
            self.assertAlmostEqual(value, self.BASELINE_SHORTFALL, delta=0.0005)
        self.assertLess(max(shortfalls) - min(shortfalls), 0.0005)

    def test_the_residual_gate_is_no_longer_quieted_by_the_bias(self) -> None:
        """``face_residual_rms`` was taken about a mean the window had
        already pulled, so a truncated sample looked *tighter*: 10.00 mm at a
        30 mm offset down to 4.67 mm at 70 mm. The shape gate got quieter
        exactly as the face got further from the model."""
        readings = [
            self._run(self._at_offset(mm / 1000.0)).face_residual_rms
            for mm in (0, 20, 30, 40, 50, 55)
        ]
        for rms in readings:
            self.assertAlmostEqual(rms, 0.010, delta=0.0015)
        self.assertLess(max(readings) - min(readings), 0.0005)

    def test_a_face_past_the_declared_reach_is_refused_not_shrunk(self) -> None:
        """Past ``max_face_recentre`` the honest answer is that this
        instrument was not set up to measure a deviation this large. Pinned,
        70 mm was answered with 53.9 and every gate passed."""
        for delta_mm in (70, 80):
            with self.subTest(offset_mm=delta_mm):
                with self.assertRaises(LikelihoodCalibrationError) as caught:
                    self._run(self._at_offset(delta_mm / 1000.0))
                self.assertIn("from where the model puts it", str(caught.exception))

    def test_the_refusal_says_how_far_off_the_face_actually_is(self) -> None:
        """A refusal naming the distance is a finding. One that does not is a
        dead end, and the distance is precisely what the pinned window could
        not produce."""
        with self.assertRaises(LikelihoodCalibrationError) as caught:
            self._run(self._at_offset(0.080))
        self.assertRegex(str(caught.exception), r"\b(78|79|80|81) mm\b")

    def test_a_deviation_the_window_used_to_hide_now_reaches_the_innovation_gate(
        self,
    ) -> None:
        """A shrunken deviation is a shrunken innovation. At 60 mm the pinned
        window reported 52.0 mm and passed the 5-sigma gate; the settled one
        puts the real number in front of it and it fires at 5.29 sigma."""
        with self.assertRaises(LikelihoodCalibrationError) as caught:
            self._run(self._at_offset(0.060))
        self.assertIn("innovation gate", str(caught.exception))

    def test_beyond_the_responsibilities_it_still_refuses_on_points(self) -> None:
        """Past about 80 mm the element's own GMM responsibilities die. That
        part always worked and must keep working -- the fix must not give the
        window a way to reach returns the registration does not assign here."""
        for delta_mm in (90, 110, 150):
            with self.subTest(offset_mm=delta_mm):
                with self.assertRaises(LikelihoodCalibrationError) as caught:
                    self._run(self._at_offset(delta_mm / 1000.0))
                self.assertIn("effective points", str(caught.exception))


class SupportWindowMechanismTests(unittest.TestCase):
    """The window-settling step and the far-face guard, on their own."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = derive_scene(GatSession.load_ifc(MODEL).world)

    BAND = 0.060

    def test_it_finds_a_plane_wherever_the_plane_is(self) -> None:
        rng = np.random.default_rng(5)
        for offset in (0.0, 0.01, -0.02, 0.045, -0.055):
            with self.subTest(offset=offset):
                proj = offset + rng.normal(0.0, 0.004, 500)
                centre, walked = _settle_support_window(
                    proj, np.ones(500), 0.0, self.BAND
                )
                self.assertAlmostEqual(centre, offset, delta=0.001)
                self.assertAlmostEqual(walked, abs(offset), delta=0.001)

    def test_an_empty_window_is_left_where_it_started(self) -> None:
        """Returning a mean over nothing would be worse than returning the
        prediction: the caller's effective-point gate then refuses with a
        count, which says what is wrong."""
        proj = np.full(50, 5.0)
        centre, walked = _settle_support_window(proj, np.ones(50), 0.0, self.BAND)
        self.assertEqual(centre, 0.0)
        self.assertEqual(walked, 0.0)

    def test_zero_weight_returns_do_not_move_it(self) -> None:
        proj = np.concatenate([np.zeros(100), np.full(100, 0.05)])
        gamma = np.concatenate([np.ones(100), np.zeros(100)])
        centre, _ = _settle_support_window(proj, gamma, 0.0, self.BAND)
        self.assertAlmostEqual(centre, 0.0, delta=1e-9)

    def test_it_terminates_on_two_clusters_it_cannot_settle_between(self) -> None:
        """Mean shift with a flat kernel oscillates between rival clusters.
        The round bound is what turns that into a bounded answer the caller
        can gate rather than a loop."""
        rng = np.random.default_rng(9)
        proj = np.concatenate([
            -0.05 + rng.normal(0.0, 0.002, 300),
            0.05 + rng.normal(0.0, 0.002, 300),
        ])
        centre, walked = _settle_support_window(proj, np.ones(600), 0.0, self.BAND)
        self.assertTrue(math.isfinite(centre))
        self.assertLessEqual(walked, 0.1)

    def test_the_far_face_guard_only_applies_when_the_far_face_is_separable(
        self,
    ) -> None:
        """It compares the settled window against one 2R outward, so the two
        have to be separate windows. Door-1 has 25 mm of support radius
        against a 60 mm band: its rival window *overlaps the face being
        measured*, and on a clean one-sided scan of it the ratio reads 0.99.
        Unguarded, the test would refuse every honest measurement of any
        element thinner than the band.
        """
        door = self.scene.element_by_name("Door-1")
        direction = np.array([1.0, 0.0, 0.0])
        radius = support_radius(door, direction)
        band = ClearanceLikelihoodCalibration().face_band
        self.assertLess(radius, band, "Door-1 is the thin case by construction")

        near = float(direction @ door.box.center() + radius)
        rng = np.random.default_rng(6)
        proj = near + rng.normal(0.0, 0.004, 300)
        gamma = np.ones_like(proj)
        centre, _ = _settle_support_window(proj, gamma, near, band)
        here = float(np.sum(gamma * (np.abs(proj - centre) <= band)))
        rival = float(
            np.sum(gamma * (np.abs(proj - (centre + 2.0 * radius)) <= band))
        )
        self.assertGreater(
            rival / here, 0.9, "the rival window overlaps the face here"
        )
        # Which is why the runtime does not ask the question at this radius.
        self.assertFalse(radius > band)

    def test_two_faces_in_one_window_are_caught_as_scatter_instead(self) -> None:
        """The thin case is not unguarded. A scanner that saw a 50 mm door
        from both rooms puts two planes in one window; the retained returns
        are bimodal, and the half-separation reads as scatter well past
        ``max_residual_sigma_ratio``. That is the gate that speaks below the
        band, and the geometric one above it."""
        door = self.scene.element_by_name("Door-1")
        direction = np.array([1.0, 0.0, 0.0])
        radius = support_radius(door, direction)
        near = float(direction @ door.box.center() + radius)
        calibration = ClearanceLikelihoodCalibration()

        rng = np.random.default_rng(5)
        proj = np.concatenate([
            near + rng.normal(0.0, 0.004, 300),
            near - 2.0 * radius + rng.normal(0.0, 0.004, 300),
        ])
        gamma = np.ones_like(proj)
        centre, _ = _settle_support_window(proj, gamma, near, calibration.face_band)
        self.assertAlmostEqual(centre, near - radius, delta=0.002)

        inside = np.abs(proj - centre) <= calibration.face_band
        weights = gamma * inside
        mass = float(weights.sum())
        observed = float(np.sum(weights * proj) / mass)
        rms = math.sqrt(float(np.sum(weights * np.square(proj - observed)) / mass))
        bound = calibration.max_residual_sigma_ratio * calibration.sensor_sigma
        self.assertGreater(
            rms, bound,
            "two faces in one window must read as scatter past the shape gate",
        )

    def test_a_separable_far_face_does_fire_the_geometric_guard(self) -> None:
        """Above the band the geometric test is the only one that can speak:
        returns on a far face 200 mm away are a clean single plane, so no
        scatter statistic sees anything wrong. Wall-Party along x is 100 mm
        of support radius against the 60 mm band."""
        wall = self.scene.element_by_name("Wall-Party")
        direction = np.array([1.0, 0.0, 0.0])
        radius = support_radius(wall, direction)
        calibration = ClearanceLikelihoodCalibration()
        self.assertGreater(radius, calibration.face_band)

        near = float(direction @ wall.box.center() + radius)
        rng = np.random.default_rng(8)
        # A pose one thickness out: the far face's returns land where the
        # model puts the near face, and the near face's land 2R outward.
        proj = np.concatenate([
            near + rng.normal(0.0, 0.004, 300),
            near + 2.0 * radius + rng.normal(0.0, 0.004, 300),
        ])
        gamma = np.ones_like(proj)
        centre, _ = _settle_support_window(proj, gamma, near, calibration.face_band)

        inside = np.abs(proj - centre) <= calibration.face_band
        weights = gamma * inside
        mass = float(weights.sum())
        observed = float(np.sum(weights * proj) / mass)
        rms = math.sqrt(float(np.sum(weights * np.square(proj - observed)) / mass))
        self.assertLess(
            rms, calibration.max_residual_sigma_ratio * calibration.sensor_sigma,
            "this is a clean plane; no scatter statistic can object",
        )

        here = float(np.sum(gamma * inside))
        rival = float(
            np.sum(gamma * (np.abs(proj - (centre + 2.0 * radius)) <= calibration.face_band))
        )
        self.assertGreaterEqual(rival / here, calibration.max_rival_plane_share)



class OnlyTheSupportFaceSpeaksForItTests(unittest.TestCase):
    """The support window is one-dimensional; a box has four faces the
    direction is perpendicular to, and their returns fall inside it.

    Wall-Party is 3.0 m tall and 0.2 m thick. Its top face is the support
    face for a +z clearance; its sides and ends run the full height, so
    every return on them within one ``face_band`` of the top landed in the
    support window. Measured on the shipped ``gat/demo/geometry`` scan, that
    is **21.3% of the weight**. Those returns are not scatter about the
    support plane -- they are a different plane seen edge-on -- and their
    spread is what ``max_residual_sigma_ratio`` was reading:

        support window            face_mass   observed   residual rms
        all returns                   36.35   2.993521      15.08 mm
        support-face returns only     28.61   2.998803       8.84 mm

    The true top is 3.000, so filtering also takes the measurement from
    6.5 mm below it to 1.2 mm below it. ``min_face_alignment`` already
    checks the *direction* names a face rather than an edge; nothing checked
    that the *returns* did.

    The demo had been passing the 15 mm shape gate at 11.96 mm, and only
    because the window was pinned 6.5 mm higher and clipped more of the
    contaminating tail. Settling the window honestly took it to 15.08 and
    refused. Both numbers were wrong; the face filter is what makes them
    agree.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = derive_scene(GatSession.load_ifc(MODEL).world)
        cls.wall = cls.scene.element_by_name("Wall-Party")

    def _box_surface(self, element, per_face: int = 400, sigma: float = 0.004):
        """Returns on all six faces of an element's box, as a real scan is."""
        rng = np.random.default_rng(3)
        rotation = rot_z(element.box.angle)
        half = 0.5 * np.asarray(element.box.extents)
        centre = np.asarray(element.box.center())
        out = []
        for axis in range(3):
            for sign in (-1.0, 1.0):
                local = rng.uniform(-half, half, size=(per_face, 3))
                local[:, axis] = sign * half[axis]
                out.append(local)
        local = np.concatenate(out)
        local += rng.normal(0.0, sigma, local.shape)
        return centre + local @ rotation.T

    def test_returns_on_perpendicular_faces_are_excluded(self) -> None:
        points = self._box_surface(self.wall)
        direction = np.array([0.0, 0.0, 1.0])
        mask = _on_support_face(self.wall, direction, points)

        # Six faces sampled equally, and exactly one of them is the support
        # face: the axis the direction names, on the side it points at. The
        # opposite face on the same axis is the element's far side, and
        # keeping it would hide a thin element's two faces inside one
        # retained set -- the case ``max_rival_plane_share`` exists to refuse.
        self.assertAlmostEqual(mask.mean(), 1.0 / 6.0, delta=0.02)

        kept = points[mask]
        top = float(direction @ self.wall.box.center()) + support_radius(
            self.wall, direction
        )
        self.assertAlmostEqual(float(kept[:, 2].mean()), top, delta=0.002)
        # And what it kept really is flat, at the sensor.
        self.assertLess(float(kept[:, 2].std()), 0.006)

    def test_the_excluded_returns_are_the_ones_that_read_as_shape(self) -> None:
        """Without the filter the retained set spans the band; with it, the
        spread is the sensor. That difference is the whole shape gate."""
        points = self._box_surface(self.wall)
        direction = np.array([0.0, 0.0, 1.0])
        band = ClearanceLikelihoodCalibration().face_band
        top = float(direction @ self.wall.box.center()) + support_radius(
            self.wall, direction
        )
        projections = points @ direction
        in_band = np.abs(projections - top) <= band
        on_face = _on_support_face(self.wall, direction, points)

        unfiltered = float(projections[in_band].std())
        filtered = float(projections[in_band & on_face].std())
        # The filtered set is the sensor; the unfiltered one is a face seen
        # edge-on mixed into it. On the shipped demo scan that difference is
        # 15.08 mm against 8.84 mm, either side of the 15 mm shape gate.
        self.assertLess(filtered, 0.006)
        self.assertGreater(unfiltered, 2.0 * filtered)

    def test_a_direction_along_the_thin_axis_picks_that_face(self) -> None:
        """The support axis is whichever local axis the direction aligns
        with, not a fixed one."""
        points = self._box_surface(self.wall)
        for direction, expect_extent in (
            (np.array([1.0, 0.0, 0.0]), 0.2),   # through the wall's thickness
            (np.array([0.0, 0.0, 1.0]), 3.0),   # up through its height
        ):
            with self.subTest(direction=tuple(direction)):
                mask = _on_support_face(self.wall, direction, points)
                self.assertAlmostEqual(mask.mean(), 1.0 / 6.0, delta=0.02)
                kept = points[mask]
                radius = support_radius(self.wall, direction)
                self.assertAlmostEqual(radius, expect_extent / 2.0, delta=1e-9)
                outer = float(direction @ self.wall.box.center()) + radius
                # Only the OUTER face on that axis, not its opposite.
                self.assertTrue(np.all(np.abs(kept @ direction - outer) < 0.02))

    def test_the_filter_makes_the_answer_independent_of_where_the_window_started(
        self,
    ) -> None:
        """The strongest evidence that it is the right filter: with it, the
        pinned window and the settled window return bit-identical numbers on
        the demo scan (mass 28.61, observed 2.998803, rms 8.84 mm). A
        correct extraction cannot depend on its own starting guess."""
        points = self._box_surface(self.wall)
        direction = np.array([0.0, 0.0, 1.0])
        band = ClearanceLikelihoodCalibration().face_band
        top = float(direction @ self.wall.box.center()) + support_radius(
            self.wall, direction
        )
        projections = points @ direction
        gamma = _on_support_face(self.wall, direction, points).astype(float)

        results = []
        for start in (top, top - 0.02, top + 0.02):
            centre, _ = _settle_support_window(projections, gamma, start, band)
            weights = gamma * (np.abs(projections - centre) <= band)
            results.append(float(np.sum(weights * projections) / weights.sum()))
        self.assertAlmostEqual(results[0], results[1], delta=1e-12)
        self.assertAlmostEqual(results[0], results[2], delta=1e-12)


if __name__ == "__main__":
    unittest.main()
