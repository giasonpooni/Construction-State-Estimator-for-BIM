"""The intended About text is well formed and drift is detected.

The live comparison needs the network, so only the pure comparison is tested
here; validation/check_about.py talks to the API when run directly.

stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
ABOUT = _ROOT / ".github" / "repo-about.json"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_about", _ROOT / "validation" / "check_about.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepoAboutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intended = json.loads(ABOUT.read_text(encoding="utf-8"))
        cls.checker = _load_checker()

    def test_about_names_cse_and_keeps_openusd_a_carrier(self) -> None:
        description = self.intended["description"]
        self.assertIn("CSE", description)
        self.assertIn("carrier", description)
        # The name this repo is not allowed to carry any more.
        self.assertNotIn("transformer", description.lower())
        self.assertNotIn("digital twin", description.lower())
        self.assertNotIn("digital-twin", description.lower())

    def test_topics_are_the_declared_set(self) -> None:
        self.assertEqual(
            sorted(self.intended["topics"]),
            ["bim", "construction", "gaussian", "ifc", "state-estimation", "verification"],
        )
        for topic in self.intended["topics"]:
            self.assertNotIn("digital", topic)

    def test_identical_metadata_reports_no_drift(self) -> None:
        live = {
            "description": self.intended["description"],
            "topics": list(reversed(self.intended["topics"])),  # order is not drift
            "homepage": self.intended["homepage"],
        }
        self.assertEqual(self.checker.compare(self.intended, live), [])

    def test_each_field_is_detected_independently(self) -> None:
        base = {
            "description": self.intended["description"],
            "topics": list(self.intended["topics"]),
            "homepage": self.intended["homepage"],
        }
        for field, mutated in (
            ("description", "Portable evidence-to-decision runtime for BIM."),
            ("topics", ["architecture", "filtering"]),
            ("homepage", ""),
        ):
            live = dict(base)
            live[field] = mutated
            self.assertEqual(self.checker.compare(self.intended, live), [field])

    def test_missing_live_fields_count_as_drift(self) -> None:
        self.assertEqual(
            sorted(self.checker.compare(self.intended, {})),
            ["description", "homepage", "topics"],
        )


if __name__ == "__main__":
    unittest.main()
