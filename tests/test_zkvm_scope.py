from __future__ import annotations

import unittest

from gat.harness.zkvm_scope import admit_guest


class ZkvmScopeTests(unittest.TestCase):
    def test_beam_line_is_admitted(self) -> None:
        row = admit_guest("beam-b1-f2-1", claim_scope="computational-integrity-only")
        self.assertTrue(row["admitted"])
        self.assertFalse(row["zero_knowledge"])

    def test_jspt_stays_out_of_the_guest(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden"):
            admit_guest("jspt-a2-a5", claim_scope="computational-integrity-only")

    def test_hiding_is_not_the_default_claim(self) -> None:
        with self.assertRaisesRegex(ValueError, "claim_scope"):
            admit_guest("beam-b1-f2-1", claim_scope="zero-knowledge")


if __name__ == "__main__":
    unittest.main()
