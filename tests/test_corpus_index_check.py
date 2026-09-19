"""The index's claims about sibling corpora are checkable.

validation/invariant-corpus-index-v2.json asserts twelve members, their needles
and the chart each needle lives in. check_corpus_index.py verifies that against
real clones; these tests cover its logic against fixtures so CI guards the
checker without needing any companion checked out.

stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
INDEX = _ROOT / "validation" / "invariant-corpus-index-v2.json"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_corpus_index", _ROOT / "validation" / "check_corpus_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(repo="Sibling", needle="var.thing", chart="chart.sibling", role="cite"):
    return {"repo": repo, "role": role, "needles": [needle], "charts": {needle: chart}}


def _corpus(
    *, schema="invariant-corpus-v2", needle="var.thing", chart="chart.sibling",
    cites="giasonpooni/Construction-State-Estimator-for-BIM",
    claim_scope="computational-integrity-only",
):
    coordinate = {"id": needle, "quantity": "thing"}
    if chart is not None:
        coordinate["chart"] = chart
    document = {
        "schema": schema,
        "claim_scope": claim_scope,
        "invariants": [{"id": "inv.one", "kind": "identity"}],
        "free_coordinates": [coordinate],
    }
    if cites is not None:
        document["cites"] = cites
    return document


class IndexSelfConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load()

    def test_the_shipped_index_is_self_consistent(self) -> None:
        self.assertEqual(self.check.check_index(self.check.load_index()), [])

    def test_a_duplicate_chart_is_caught(self) -> None:
        index = {
            "members": [
                _row("A", "var.a", "chart.same"),
                _row("B", "var.b", "chart.same"),
                _row("C", "var.c", "chart.c", role="canonical"),
            ]
        }
        problems = self.check.check_index(index)
        self.assertTrue(any("claimed by" in p for p in problems))

    def test_a_needle_without_a_chart_is_caught(self) -> None:
        index = {"members": [{"repo": "A", "role": "canonical", "needles": ["var.a"], "charts": {}}]}
        self.assertTrue(any("no chart" in p for p in self.check.check_index(index)))

    def test_exactly_one_canonical_member_is_required(self) -> None:
        two = {"members": [_row("A", "var.a", "chart.a", role="canonical"),
                           _row("B", "var.b", "chart.b", role="canonical")]}
        self.assertTrue(any("canonical" in p for p in self.check.check_index(two)))
        none = {"members": [_row("A", "var.a", "chart.a")]}
        self.assertTrue(any("canonical" in p for p in self.check.check_index(none)))


class MemberCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load()

    def _repo(self, tmp: str, document: dict | None, name="invariant-corpus-v2.json") -> Path:
        repo = Path(tmp) / "Sibling"
        (repo / "validation").mkdir(parents=True)
        if document is not None:
            (repo / "validation" / name).write_text(json.dumps(document), encoding="utf-8")
        return repo

    def test_a_matching_corpus_has_no_problems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus())
            self.assertEqual(self.check.check_member(_row(), repo), [])

    def test_a_missing_corpus_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, None)
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("no validation/" in p for p in problems))

    def test_a_chart_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(chart="chart.somewhere-else"))
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("the index claims" in p for p in problems))

    def test_a_missing_needle_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(needle="var.other"))
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("index claims" in p for p in problems))

    def test_a_sibling_must_cite_the_canonical_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(cites="giasonpooni/Something-Else"))
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("canonical repo" in p for p in problems))

    def test_the_canonical_member_need_not_cite_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(cites=None))
            self.assertEqual(self.check.check_member(_row(role="canonical"), repo), [])

    def test_a_widened_claim_scope_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(claim_scope="field-evidence"))
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("claim_scope" in p for p in problems))

    def test_v2_without_a_chart_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, _corpus(chart=None))
            problems = self.check.check_member(_row(), repo)
            self.assertTrue(any("declares no chart" in p for p in problems))

    def test_an_unmigrated_v1_sibling_is_not_a_contradiction(self) -> None:
        # Companions migrate on their own commits; a v1 corpus carries no chart
        # and that must read as "not yet", not as a broken claim.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(
                tmp,
                _corpus(schema="invariant-corpus-v1", chart=None),
                name="invariant-corpus-v1.json",
            )
            self.assertEqual(self.check.check_member(_row(), repo), [])


if __name__ == "__main__":
    unittest.main()
