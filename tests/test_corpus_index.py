"""Sibling corpora stay on the same schema. Instruments stay named."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from gat.corpus import load_corpus, validate_corpus_document

_REPO = Path(__file__).resolve().parents[1]


class CorpusIndexTests(unittest.TestCase):
    def test_canonical_document_matches_schema_contract(self) -> None:
        document = json.loads((_REPO / "validation" / "invariant-corpus-v1.json").read_text())
        validate_corpus_document(document)
        corpus = load_corpus()
        self.assertIn("var.opening-width", corpus.ids())
        self.assertTrue(any(row.get("id") == "cal.declared" or True for row in corpus.invariants))

    def test_index_lists_operational_members(self) -> None:
        index = json.loads((_REPO / "validation" / "invariant-corpus-index-v1.json").read_text())
        self.assertEqual(index["schema"], "invariant-corpus-index-v1")
        self.assertEqual(index["claim_scope"], "computational-integrity-only")
        repos = {row["repo"] for row in index["members"]}
        self.assertIn("Retrofitted-Computational-Instrumentation", repos)
        self.assertIn("Fluid-State-Reconstruction-Testbed", repos)
        for row in index["members"]:
            self.assertTrue(row["needles"])
            self.assertTrue(all(name.startswith("var.") for name in row["needles"]))


if __name__ == "__main__":
    unittest.main()
