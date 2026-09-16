from __future__ import annotations

import unittest

from gat.harness.zkvm_numerics import admit_numeric_profile


class GuestNumericsTests(unittest.TestCase):
    def test_beam_checked_integer_is_admitted(self) -> None:
        row = admit_numeric_profile(
            {"arithmetic": "checked-integer", "guest_id": "beam-b1-f2-1"}
        )
        self.assertTrue(row["admitted"])
        self.assertEqual(row["quantize_on"], "host")

    def test_float64_geodesic_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "IEEE-754"):
            admit_numeric_profile({"arithmetic": "float64", "guest_id": "geodesic"})

    def test_unopened_kernel_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "implemented"):
            admit_numeric_profile(
                {"arithmetic": "checked-integer", "guest_id": "discrete-jacobi-field"}
            )


if __name__ == "__main__":
    unittest.main()
