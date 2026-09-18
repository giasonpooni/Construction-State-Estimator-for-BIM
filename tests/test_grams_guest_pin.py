"""GAT reads the JSPT grams guest receipt verbatim.

Requires the companion ``sensitivity`` clone; skipped when it is absent.
stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import unittest


def sensitivity_available() -> bool:
    """True when the companion JSPT clone is importable."""
    try:
        return importlib.util.find_spec("sensitivity") is not None
    except (ImportError, ValueError):
        return False


@unittest.skipUnless(sensitivity_available(), "companion JSPT clone is not importable")
class GramsGuestPinTests(unittest.TestCase):
    def test_gat_reads_jspt_grams_receipt(self) -> None:
        from sensitivity.grams_guest import receipt

        body = receipt()
        self.assertEqual(body["verdict"], "PASS")
        self.assertEqual(body["profile"], "grams-micro-v1")
        self.assertEqual(body["P_prime"][0][0], 1_000_000.0)


if __name__ == "__main__":
    unittest.main()
