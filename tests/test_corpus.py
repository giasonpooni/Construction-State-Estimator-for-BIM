"""Corpus is I. Inference only needles named free coordinates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.corpus import CorpusError, load_corpus
from gat.demo.present_process import run_process
from gat.demo.present_space import OFFICE_A, present_space
from gat.demo.present_space import _DEMO_IFC, _DEMO_RECEIPT, _DEMO_SPACE


class CorpusTests(unittest.TestCase):
    def test_office_a_and_pin_are_in_i(self) -> None:
        corpus = load_corpus()
        self.assertIn("id.office-a", corpus.ids())
        self.assertIn(OFFICE_A, corpus.global_ids())
        self.assertEqual(corpus.require("pin.chain-jvp-i32")["y"], [5, 3])
        self.assertFalse(corpus.require("gate.sp1-refuse")["allowed"])

    def test_needle_only_free_coordinates(self) -> None:
        corpus = load_corpus()
        pointed = corpus.needle("var.opening-width")
        self.assertTrue(pointed["may_observe"])
        with self.assertRaisesRegex(CorpusError, "invariant"):
            corpus.needle("disp.three-valued")
        with self.assertRaisesRegex(CorpusError, "not in the invariant corpus"):
            corpus.require("var.invented-from-a-scan")

    def test_present_space_attaches_corpus_membership(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            payload = present_space(
                model_path=_DEMO_IFC,
                space_path=_DEMO_SPACE,
                receipt_path=_DEMO_RECEIPT,
                output_path=f"{raw}/present.json",
            )
        self.assertTrue(payload["corpus"]["space_in_corpus"])
        self.assertEqual(payload["corpus"]["schema"], "invariant-corpus-v1")
        self.assertIn("var.opening-width", payload["corpus"]["needles"])

    def test_unknown_guid_opens_corpus_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            space = Path(raw) / "space.json"
            space.write_text(
                json.dumps(
                    {
                        "space_id": "space:ifc:NOTINCORPUS000000000",
                        "space_ref": {
                            "ifc_class": "IfcSpace",
                            "global_id": "NOTINCORPUS000000000",
                            "name": "Invented",
                        },
                    }
                )
            )
            payload = present_space(
                model_path=_DEMO_IFC,
                space_path=space,
                receipt_path=_DEMO_RECEIPT,
            )
        self.assertFalse(payload["corpus"]["space_in_corpus"])
        codes = {row["code"] for row in payload["open_requests"]}
        self.assertIn("corpus.identity", codes)
        self.assertEqual(payload["inspectability"], "REQUEST_EVIDENCE")

    def test_present_packet_lists_the_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = run_process(output_dir=raw)
            listed = json.loads((Path(raw) / "07-corpus.json").read_text())
        self.assertTrue(manifest["corpus"]["space_in_corpus"])
        self.assertIn("07-corpus", manifest["steps"])
        self.assertIn("id.office-a", listed["invariants"])


if __name__ == "__main__":
    unittest.main()
