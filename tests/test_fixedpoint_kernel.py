"""i32 kernels stay integer and match the pinned claim."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from gat.satellites.fixedpoint_kernel import (
    chain_jvp_i32,
    discrete_lyapunov_decrease_i32,
)

PIN = Path(__file__).resolve().parents[1] / "validation" / "sp1-kernel-i32-v0.json"


class FixedpointKernelTests(unittest.TestCase):
    def test_chain_jvp_matches_pin(self) -> None:
        pin = json.loads(PIN.read_text())["kernels"]["chain_jvp_i32"]
        y = chain_jvp_i32(pin["J1"], pin["dx"], pin["J2"])
        self.assertEqual(list(y), pin["y"])

    def test_lyapunov_decrease_matches_pin(self) -> None:
        pin = json.loads(PIN.read_text())["kernels"]["discrete_lyapunov_decrease_i32"]
        report = discrete_lyapunov_decrease_i32(pin["A"], pin["P"], pin["x"])
        self.assertEqual(report["V"], pin["V"])
        self.assertEqual(report["V_next"], pin["V_next"])
        self.assertTrue(report["decreases"])

    def test_float_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            chain_jvp_i32([[1.0, 0], [0, 1]], [1, 0], [[1, 0], [0, 1]])
        with self.assertRaises(TypeError):
            discrete_lyapunov_decrease_i32([[0, 1], [0, 0]], [[1, 0], [0, 1]], [2.0, 1])


if __name__ == "__main__":
    unittest.main()
