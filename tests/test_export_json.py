"""GatSession.export_json writes the world, not just a file.

The facade method was restored with the rest of the facade, and the only thing
asserting it was the pipeline demo checking that state.json exists. Existence is
not a contract: this pins that the document describes the world it came from.

stdlib unittest only.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.adapters.json_io import world_to_dict
from gat.engine.transform import ObserveQuantity
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
MODEL = _ROOT / "gat" / "demo" / "model.ifc"


class ExportJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(str(MODEL))

    def _dump(self, session: GatSession) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            self.assertIsNone(session.export_json(str(path)))
            return json.loads(path.read_text(encoding="utf-8"))

    def test_the_document_matches_the_adapter(self) -> None:
        self.assertEqual(self._dump(self.session), world_to_dict(self.session.world))

    def test_it_is_deterministic(self) -> None:
        self.assertEqual(self._dump(self.session), self._dump(self.session))

    def test_it_creates_the_parent_directory_or_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "missing" / "state.json"
            try:
                self.session.export_json(str(nested))
            except FileNotFoundError:
                pass  # refusing to invent a directory is a fine contract
            else:
                self.assertTrue(nested.is_file())

    def test_an_observation_changes_the_exported_state(self) -> None:
        before = self._dump(self.session)
        session = GatSession.load_ifc(str(MODEL))
        session.run(
            ObserveQuantity.single(session.var("Office-A", "Volume"), 59.4, 0.05)
        )
        after = self._dump(session)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
