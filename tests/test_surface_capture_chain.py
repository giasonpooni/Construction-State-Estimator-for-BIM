"""The scan chain end to end on a capture a scanner could have produced.

Every other test in this repository feeds the chain
:func:`synthesize_scan`, which draws points from the model's own Gaussian
mixture. That makes the estimator's job well posed by construction: the
data really does come from the density being fitted. A real capture does
not, and the difference is not noise, it is a bias.

The model's elements are solids. A wall is a 0.3 m slab and its Gaussians
fill that slab; a scanner sees one face of it. Fitting face returns to a
volume pulls the model toward the side that was measured, by something like
half the thickness, and the fit's own information matrix cannot see it --
the optimum is sharp, it is just in the wrong place. Measured here: the
pose lands ~0.15 m out while ``pose_sigma`` reports ~6 mm.

That is the case the chain is built for. ``pose_sigma`` is documented as a
lower bound, the registration is not trusted on its own, and conditioning a
belief requires an independent pose whose agreement with the fit is
checked. This module asserts the whole sequence: the capture registers, the
registration is confidently wrong, and the independent check refuses it
before any belief moves.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

import gat.demo
from gat.errors import GatError
from gat.geometry import (
    ClearanceDecision,
    ClearanceLikelihoodCalibration,
    IndependentPoseCalibration,
    OrientedBox,
    adapt_clearance_likelihood,
    assess_clearance,
    plan_clearance_evidence,
    scan_filter,
    synthesize_scan,
)
from gat.geometry.registration import (
    MAX_TRANSLATION_SIGMA,
    RigidTransformZ,
    ScanRegistrar,
)
from gat.geometry.scan_io import load_ply_points
from gat.geometry.scan_likelihood import _pose_disagreement_m2
from gat.geometry.stateio import derive_scene, rot_z
from gat.session import GatSession

from tests.surface_capture import capture_station, scene_slabs, slab, write_ply

MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

#: Where the scanner stood: one station in each office and two in the middle,
#: which is how a two-room storey gets covered.
STATIONS = (
    (2.0, 2.0, 1.55),
    (7.2, 2.0, 1.55),
    (4.6, 0.8, 1.55),
    (4.6, 3.4, 1.55),
)

#: Furniture and a person: in the room, not in the model.
CLUTTER = (
    ((3.2, 3.0, 0.0), 0.0, (0.6, 0.6, 0.75)),
    ((1.2, 0.9, 0.0), 0.3, (0.45, 0.30, 1.75)),
    ((7.0, 1.0, 0.0), 1.1, (0.8, 0.5, 0.9)),
)

#: The frame the scanner worked in, withheld from the registrar.
TRUTH = RigidTransformZ(theta=math.radians(23.0), t=(1.4, -0.7, 0.11))

#: Coarser than the module default: pose wants coverage, not density, and
#: this keeps one honest registration affordable in the suite.
POSE_VOXEL_M = 0.50

_CACHE: dict = {}


def _fixture() -> dict:
    """One survey, one registration, computed once per test process."""
    if not _CACHE:
        session = GatSession.load_ifc(MODEL)
        scene = derive_scene(session.world)
        boxes = scene_slabs(scene) + [slab(*item) for item in CLUTTER]
        survey = np.vstack(
            [
                capture_station(boxes, station, seed=11 + index)
                for index, station in enumerate(STATIONS)
            ]
        )

        # Out to a real binary PLY and back through the shipped loader, so
        # the chain is entered the way a producer artifact enters it.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "survey.ply"
            write_ply(path, survey)
            loaded = load_ply_points(path)

        # The capture is in the scanner's own frame; the model frame is what
        # registration has to recover.
        scanner_frame = (loaded - np.asarray(TRUTH.t)) @ rot_z(TRUTH.theta)
        filtered = scan_filter.prepare_for_pose(scanner_frame, voxel_m=POSE_VOXEL_M)
        registrar = ScanRegistrar(scene)
        result = registrar.register(filtered.points)
        _CACHE.update(
            session=session,
            scene=scene,
            boxes=boxes,
            survey=survey,
            loaded=loaded,
            filtered=filtered,
            registrar=registrar,
            result=result,
        )
    return _CACHE


class SurfaceCaptureTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = _fixture()
        cls.scene = fixture["scene"]
        cls.boxes = fixture["boxes"]
        cls.survey = fixture["survey"]
        cls.loaded = fixture["loaded"]
        cls.filtered = fixture["filtered"]
        cls.registrar = fixture["registrar"]
        cls.result = fixture["result"]


class IngestionTests(SurfaceCaptureTestBase):
    """A producer artifact reaches the estimator intact."""

    def test_the_survey_survives_the_ply_round_trip(self) -> None:
        self.assertEqual(self.loaded.shape, self.survey.shape)
        self.assertEqual(self.loaded.dtype, np.float64)
        # float32 on the wire: the loader promotes without claiming the bits
        # the producer did not write.
        self.assertLess(np.abs(self.loaded - self.survey).max(), 1.0e-5)

    def test_the_filter_declares_what_it_removed(self) -> None:
        steps = {step.method for step in self.filtered.steps}
        self.assertIn("density_outlier_removal", steps)
        self.assertIn("voxel_downsample", steps)
        self.assertLess(self.filtered.point_count, self.survey.shape[0] / 10)
        self.assertNotEqual(self.filtered.digest, self.filtered.source_digest)

    def test_the_stray_returns_are_dropped_before_the_estimator(self) -> None:
        """The ghosts are metres from any surface; the density filter is what
        removes them, and it says how many."""
        removal = next(
            step for step in self.filtered.steps
            if step.method == "density_outlier_removal"
        )
        self.assertGreater(removal.points_in - removal.points_out, 0)


class SurfaceBiasTests(SurfaceCaptureTestBase):
    """The fit is confident and wrong, which is why it is not trusted alone."""

    def test_the_capture_registers_and_is_accepted(self) -> None:
        self.assertTrue(self.result.accepted, self.result.refusal)
        self.assertGreaterEqual(self.result.basin_margin, 0.10)
        self.assertGreater(self.result.basin_count, 1)

    def test_the_pose_is_out_by_far_more_than_it_reports(self) -> None:
        """Face returns against volume Gaussians pull the model toward the
        measured side. The information matrix is local curvature at the
        optimum it found, so it certifies a sharp fit in the wrong place."""
        _, translation = self.result.transform.compose_error(TRUTH)
        sigma = self.result.pose_sigma()
        worst_sigma = max(sigma[1:])

        self.assertGreater(translation, 0.05)
        self.assertLess(translation, 0.5)
        self.assertGreater(
            translation,
            10.0 * worst_sigma,
            "if the fit's own sigma covered this error the independent pose "
            "check below would be redundant; it is not",
        )
        # Still inside the pose-uncertainty gate: that gate catches a fit
        # with too little evidence, not one with biased evidence.
        self.assertLess(worst_sigma, MAX_TRANSLATION_SIGMA)

    def test_a_volumetric_scan_of_the_same_model_is_not_biased(self) -> None:
        """The bias belongs to surface capture, not to the registrar. Drawn
        from the mixture being fitted, the same estimator lands an order of
        magnitude closer with a comparable sigma."""
        drawn = synthesize_scan(
            self.scene, n_points=4000, noise_sigma=0.01,
            outlier_frac=0.02, transform=TRUTH, seed=7,
        )
        volumetric = self.registrar.register(drawn)
        _, volumetric_error = volumetric.transform.compose_error(TRUTH)
        _, surface_error = self.result.transform.compose_error(TRUTH)

        self.assertTrue(volumetric.accepted)
        self.assertLess(volumetric_error, 0.03)
        self.assertGreater(surface_error, 3.0 * volumetric_error)


class IndependentPoseRefusalTests(SurfaceCaptureTestBase):
    """Nothing is conditioned on the biased pose. This is the gate that holds."""

    def _control(self) -> IndependentPoseCalibration:
        return IndependentPoseCalibration(
            transform=TRUTH,
            covariance=np.diag(
                [math.radians(0.06) ** 2, 0.010**2, 0.010**2, 0.003**2]
            ),
            scan_digest=self.result.scan_digest,
            source_id="total-station control network",
        )

    def _plan(self):
        evidence = self.registrar.evidence(self.filtered.points, self.result)
        duct = OrientedBox(
            origin=(4.0, 1.8, 3.06), angle=0.0, extents=(3.0, 0.4, 0.4)
        )
        clearance = assess_clearance(
            self.scene,
            ClearanceDecision(
                duct, required_clearance=0.05, confidence=0.95,
                position_sigma=0.002, label="borderline MEP route",
            ),
        )
        return evidence, clearance, plan_clearance_evidence(clearance, evidence)

    def test_the_capture_does_produce_evidence_and_a_plan(self) -> None:
        """The refusal below has to be the pose check and not an empty plan."""
        evidence, clearance, plan = self._plan()
        self.assertGreater(evidence.inlier_effective_points, 0.0)
        self.assertGreater(len(evidence.elements), 1)
        self.assertFalse(clearance.resolved)
        self.assertIsNotNone(plan.selected)

    def test_survey_control_refuses_to_certify_the_biased_pose(self) -> None:
        evidence, _, plan = self._plan()
        with self.assertRaises(GatError) as caught:
            adapt_clearance_likelihood(
                self.scene, self.registrar, self.filtered.points, self.result,
                evidence, plan, self._control(),
                ClearanceLikelihoodCalibration(calibration_sigma=0.003),
            )
        self.assertIn("independent pose disagrees", str(caught.exception))

    def test_the_disagreement_is_decisive_not_marginal(self) -> None:
        """A 0.15 m error against a 10 mm control sigma is not a close call.

        Read directly rather than off a loosened run: relaxing the pose gate
        to reach the number lets the capture fall through to the face gates,
        which refuse it for their own reasons and would mask this one.
        """
        default = ClearanceLikelihoodCalibration(calibration_sigma=0.003)
        m2 = _pose_disagreement_m2(self.result, self._control())
        self.assertGreater(m2, 10.0 * default.max_pose_disagreement_m2)

    def test_a_thinner_capture_is_still_refused_further_down(self) -> None:
        """The pose check is decisive here, not everywhere, and the chain does
        not rest on it alone.

        Halve the density again and the fit lands closer by luck: m2 falls to
        about 15 against a gate of 16, and the pose check would let it by. The
        capture is still refused, by the face-mass gate, because 350 points
        over a building leave nothing on the face being measured. Asserting
        only the pose check would read as a guarantee the chain does not make.
        """
        thin = scan_filter.prepare_for_pose(
            (self.loaded - np.asarray(TRUTH.t)) @ rot_z(TRUTH.theta), voxel_m=0.70
        )
        result = self.registrar.register(thin.points)
        self.assertTrue(result.accepted, result.refusal)

        control = IndependentPoseCalibration(
            transform=TRUTH,
            covariance=np.diag(
                [math.radians(0.06) ** 2, 0.010**2, 0.010**2, 0.003**2]
            ),
            scan_digest=result.scan_digest,
            source_id="total-station control network",
        )
        evidence = self.registrar.evidence(thin.points, result)
        duct = OrientedBox(
            origin=(4.0, 1.8, 3.06), angle=0.0, extents=(3.0, 0.4, 0.4)
        )
        clearance = assess_clearance(
            self.scene,
            ClearanceDecision(
                duct, required_clearance=0.05, confidence=0.95,
                position_sigma=0.002, label="borderline MEP route",
            ),
        )
        plan = plan_clearance_evidence(clearance, evidence)
        with self.assertRaises(GatError) as caught:
            adapt_clearance_likelihood(
                self.scene, self.registrar, thin.points, result, evidence, plan,
                control, ClearanceLikelihoodCalibration(calibration_sigma=0.003),
            )
        self.assertIn("effective points", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
