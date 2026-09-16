from __future__ import annotations

import unittest
from pathlib import Path

from gat.satellites.kernel_cost import cost_chain_jvp, cost_lyapunov, cost_report


class KernelCostTests(unittest.TestCase):
    def test_pins_match_host_kernels(self) -> None:
        self.assertEqual(cost_chain_jvp().muls, 8)
        self.assertFalse(cost_lyapunov().ieee754)

    def test_report_does_not_invent_cycles(self) -> None:
        document = cost_report(Path(__file__).resolve().parents[1])
        self.assertIsNone(document["beam_guest"]["cycles"])
        self.assertFalse(document["ieee754_guest"])
        self.assertFalse(document["riscv_ot"]["flashed"])


if __name__ == "__main__":
    unittest.main()
