"""Second callback commits statement_digest. Host eval is not a proof."""

from __future__ import annotations

import unittest

from gat.proof_manifest import PROOF_CLAIM_SCOPE
from gat.sp1_kernel import (
    CALLBACK_ID,
    CLAIM_SCOPE,
    evaluate_host,
    host_callback,
    statement_digest,
)


class KernelCallbackTests(unittest.TestCase):
    def test_scope_matches_manifest_contract(self) -> None:
        self.assertEqual(CLAIM_SCOPE, PROOF_CLAIM_SCOPE)
        self.assertEqual(CLAIM_SCOPE, "computational-integrity-only")

    def test_statement_digest_is_stable(self) -> None:
        first = statement_digest()
        second = statement_digest()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_host_evaluation_is_not_a_proof(self) -> None:
        host = evaluate_host()
        self.assertEqual(host["y"], [5, 3])
        self.assertFalse(host["is_proof"])
        report = host_callback(None)
        self.assertEqual(report.document["callback_id"], CALLBACK_ID)
        self.assertEqual(report.document["statement_digest"], statement_digest())
        self.assertEqual(report.document["status"], "NOT_A_PROOF")
        self.assertFalse(report.is_proof)
        self.assertFalse(report.document["invoked"])

    def test_missing_executable_is_not_a_proof(self) -> None:
        report = host_callback("/tmp/does-not-exist-gat-sp1-kernel")
        self.assertFalse(report.is_proof)
        self.assertEqual(report.document["status"], "NOT_A_PROOF")


if __name__ == "__main__":
    unittest.main()
