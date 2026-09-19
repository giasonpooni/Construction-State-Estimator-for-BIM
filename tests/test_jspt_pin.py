"""The JSPT ownership pin is a contract, not a note.

validation/jspt-pin-v1.json declares that JSPT owns first_order_covariance
and chart law A3, consumed one way. Nothing read that file, so the claim was
unenforced in both directions: CSE could drift from the algebra it cites, and
JSPT's own corpus row alg.no-duplicate ("adapter lands only if local
TFT-1 / TPT-T is deleted in the same PR") could not be satisfied.

It cannot be satisfied by deletion. gat/engine/propagate.py forms
J @ Sigma @ J.T inline because the index rule for this portfolio is "each
repo keeps local I. none import another runtime" -- making the kernel's hot
path import the companion would break that, and the kernel also reuses the
intermediate J @ Sigma, which the JSPT entry point does not return.

So the pin is enforced the way the Python/Rust fixed-point agreement already
is: keep the local algebra and assert it agrees with the owner. The numeric
half runs only where the companion clone is importable; the contract half
always runs.

stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path

import numpy as np

from gat.gaussian.linalg import symmetrize
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
PIN = _ROOT / "validation" / "jspt-pin-v1.json"
MODEL = _ROOT / "gat" / "demo" / "model.ifc"


def sensitivity_available() -> bool:
    try:
        return importlib.util.find_spec("sensitivity") is not None
    except (ImportError, ValueError):
        return False


class JsptPinContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads(PIN.read_text(encoding="utf-8"))

    def test_pin_identifies_the_owner_at_a_commit(self) -> None:
        self.assertEqual(self.pin["schema"], "notation-systems-jspt-pin-v1")
        self.assertIn("Jacobian-Sensitivity-Propagation-Testbed", self.pin["repo"])
        sha = self.pin["sha"]
        self.assertEqual(len(sha), 40, "pin must name a full commit, not a branch")
        self.assertTrue(
            all(char in "0123456789abcdef" for char in sha),
            "pin sha must be lowercase hex",
        )

    def test_covariance_law_and_chart_law_are_owned_upstream(self) -> None:
        owns = self.pin["owns"]
        self.assertIn("first_order_covariance", owns)
        self.assertIn("chart law A3", owns)
        self.assertIn("jacobian_at", owns)
        self.assertIn("jvp", owns)

    def test_consumption_stays_one_way(self) -> None:
        # CSE cites JSPT. JSPT must never depend on CSE, or the two repos stop
        # being separately replayable.
        self.assertEqual(self.pin["consumption"], "one-way")

    def test_pin_forbids_a_third_derivative_implementation(self) -> None:
        forbidden = self.pin["forbidden"]
        self.assertIn("third finite_difference", forbidden)
        self.assertIn("sensitivity in guest", forbidden)

    def test_cse_declares_no_runtime_dependency_on_the_companion(self) -> None:
        # One-way citation is not vendoring: the companion must stay a separate
        # clone, so it may never appear in this project's dependencies.
        pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for name in ("sensitivity", "jacobian-sensitivity"):
            self.assertNotIn(
                f'"{name}', pyproject, f"{name} must not become a CSE dependency"
            )


@unittest.skipUnless(sensitivity_available(), "companion JSPT clone is not importable")
class JsptAgreementTests(unittest.TestCase):
    """The kernel's local pushforward must equal the algebra CSE cites."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = GatSession.load_ifc(str(MODEL)).world

    def test_full_view_covariance_matches_jspt_bitwise(self) -> None:
        from sensitivity.covariance import first_order_covariance

        jacobian = self.world.jacobian
        raw = self.world.belief.sigma
        owner = symmetrize(
            np.asarray(first_order_covariance(jacobian, raw), dtype=np.float64)
        )
        # Not allclose: a first-order pushforward is one matrix product each
        # way round, so agreement is exact. A tolerance here would hide drift.
        self.assertTrue(
            np.array_equal(self.world.full.sigma, owner),
            "kernel full-view sigma drifted from JSPT first_order_covariance",
        )

    def test_local_algebra_is_the_same_expression_the_owner_computes(self) -> None:
        from sensitivity.covariance import first_order_covariance

        jacobian = self.world.jacobian
        raw = self.world.belief.sigma
        local = symmetrize((jacobian @ raw) @ jacobian.T)
        owner = symmetrize(
            np.asarray(first_order_covariance(jacobian, raw), dtype=np.float64)
        )
        self.assertTrue(np.array_equal(local, owner))

    def test_chart_push_is_consistent_with_the_pushforward(self) -> None:
        # chart law A3: pushing a covariance through an invertible chart and
        # back must return it, which is what makes a chart change a gauge
        # choice rather than new information.
        from sensitivity.coordinates import push_covariance

        raw = self.world.belief.sigma
        n = raw.shape[0]
        chart = np.diag(np.linspace(1.0, 2.0, n))
        pushed = np.asarray(push_covariance(chart, raw), dtype=np.float64)
        restored = np.asarray(
            push_covariance(chart, pushed, inverse=True), dtype=np.float64
        )
        self.assertTrue(np.allclose(restored, raw, rtol=1e-12, atol=1e-12))


if __name__ == "__main__":
    unittest.main()
