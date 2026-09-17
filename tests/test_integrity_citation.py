"""Citations point at proofs. They are not proofs and not USD payloads."""

from __future__ import annotations

import tempfile
import unittest

from gat.adapters.integrity_citation import (
    CITATION_SCHEMA,
    kernel_citation,
    validate_citation,
)
from gat.demo.present_process import run_process
from gat.sp1_kernel import statement_digest


class IntegrityCitationTests(unittest.TestCase):
    def test_kernel_citation_is_integrity_only(self) -> None:
        citation = kernel_citation()
        validate_citation(citation)
        self.assertEqual(citation["schema"], CITATION_SCHEMA)
        self.assertEqual(citation["statement_digest"], statement_digest())
        self.assertEqual(citation["claim_scope"], "computational-integrity-only")
        self.assertFalse(citation["is_proof"])
        self.assertFalse(citation["in_usd_bytes"])
        self.assertFalse(citation["conditions_belief"])
        self.assertFalse(citation["may_authorize"])

    def test_proof_bytes_in_usd_are_refused(self) -> None:
        bad = kernel_citation()
        bad["in_usd_bytes"] = True
        with self.assertRaisesRegex(ValueError, "must not live in USD"):
            validate_citation(bad)

    def test_present_packet_cites_the_kernel_without_proving(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = run_process(output_dir=raw, public_xref=True)
        citation = next(
            row for row in manifest["citations"] if row["kind"].startswith("sp1-kernel")
        )
        self.assertFalse(citation["is_proof"])
        self.assertEqual(citation["statement_digest"], statement_digest())
        self.assertFalse(manifest["may_authorize"])


if __name__ == "__main__":
    unittest.main()
