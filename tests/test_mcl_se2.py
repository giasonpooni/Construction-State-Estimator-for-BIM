"""SE(2) MCL satellite. Does not touch kernel dispositions."""

from __future__ import annotations

import math
import unittest

import numpy as np

from gat.localize import se2
from gat.localize.filter import MotionNoise, ParticleFilter
from gat.localize.floor import corridor_path, room_a_pose, two_room_grid
from gat.localize.residual import residual, synthesize_scan
from gat.satellites.scan_residual_i32 import residual_i32, sse_i32


class Se2Tests(unittest.TestCase):
    def test_compose_inverse(self) -> None:
        pose = np.array([1.2, -0.4, 0.7])
        ident = se2.compose(se2.inverse(pose), pose)
        self.assertTrue(np.allclose(ident[:2], 0.0, atol=1e-12))
        self.assertLess(abs(float(ident[2])), 1e-12)

    def test_unicycle_straight(self) -> None:
        pose = np.array([0.0, 0.0, 0.0])
        nxt = se2.compose(pose, se2.unicycle_increment(1.0, 0.0, 0.5))
        self.assertAlmostEqual(float(nxt[0]), 0.5, places=12)
        self.assertAlmostEqual(float(nxt[1]), 0.0, places=12)


class ResidualTests(unittest.TestCase):
    def test_likelihood_peaks_at_true_pose(self) -> None:
        grid = two_room_grid(0.05)
        pose = np.array(room_a_pose())
        rng = np.random.default_rng(3)
        angles = np.linspace(-1.0, 1.0, 15)
        scan = synthesize_scan(pose, grid, angles, 5.0, 0.01, rng)
        here = float(np.dot(residual(pose, scan, grid), residual(pose, scan, grid)))
        shifted = residual(pose + np.array([0.6, 0.0, 0.0]), scan, grid)
        self.assertLess(here, float(np.dot(shifted, shifted)))

    def test_i32_sse_matches_python(self) -> None:
        r = residual_i32([100, 80, 0], [90, 80, 5])
        self.assertEqual(r, (10, 0, -5))
        self.assertEqual(sse_i32(r), 100 + 0 + 25)

    def test_i32_refuses_float(self) -> None:
        with self.assertRaises(TypeError):
            sse_i32([1.0])


class FilterTests(unittest.TestCase):
    def test_weights_normalize(self) -> None:
        grid = two_room_grid(0.05)
        rng = np.random.default_rng(1)
        filt = ParticleFilter.around(np.array(room_a_pose()), 64, rng, MotionNoise(0.2, 0.2, 0.2))
        scan = synthesize_scan(np.array(room_a_pose()), grid, np.linspace(-1.0, 1.0, 11), 5.0, 0.05, rng)
        filt.update(scan, grid, 0.05)
        self.assertAlmostEqual(float(np.sum(filt.weights)), 1.0, places=12)

    def test_tracking_locks(self) -> None:
        grid = two_room_grid(0.05)
        rng = np.random.default_rng(11)
        path = corridor_path()
        filt = ParticleFilter.around(np.array(path[0]), 300, rng, MotionNoise(0.12, 0.12, 0.15))
        motion = MotionNoise(0.03, 0.01, 0.03)
        angles = np.linspace(-2.2, 2.2, 17)
        for a, b in zip(path[:-1], path[1:]):
            rel = se2.relative(np.array(a), np.array(b))
            filt.predict(float(rel[0]), float(rel[2]), 1.0, motion)
            scan = synthesize_scan(np.array(b), grid, angles, 5.0, 0.04, rng)
            filt.update(scan, grid, 0.04)
            filt.resample_if_needed(0.5)
        diag = filt.diagnostics()
        err = se2.relative(diag.mean_pose, np.array(path[-1]))
        self.assertLess(math.hypot(float(err[0]), float(err[1])), 0.40)

    def test_identical_particles_collapse_neff(self) -> None:
        rng = np.random.default_rng(0)
        pose = np.array(room_a_pose())
        filt = ParticleFilter.around(pose, 50, rng, MotionNoise(1e-12, 1e-12, 1e-12))
        filt.poses[:] = pose
        filt.weights[:] = 0.0
        filt.weights[0] = 1.0
        self.assertLess(filt.n_eff(), 1.1)


if __name__ == "__main__":
    unittest.main()
