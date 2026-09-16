from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gat.demo import complete_v0


class CompleteV0Tests(unittest.TestCase):
    def test_packet_is_complete_and_not_a_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with patch("sys.argv", ["complete_v0", "-o", raw]):
                complete_v0.main()
            status = json.loads((Path(raw) / "STATUS.json").read_text())
        self.assertTrue(status["complete"])
        self.assertFalse(status["released"])
        self.assertFalse(status["field_evidence"])
        self.assertFalse(status["full_atlas_connected"])
        self.assertTrue(status["opening_component_connected"])
        self.assertIsNone(status["sp1_cycles"])


if __name__ == "__main__":
    unittest.main()
