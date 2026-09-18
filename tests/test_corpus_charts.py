"""Every free coordinate declares the chart its declaration fixes it in.

A needle names a quantity that is free until a declaration fixes it. Two
members of the index declare var.x with quantity "state" -- PLSR fixed by a
declared plant A, the State-Estimation-Testbed by a declared observation H --
so the needle id alone is not an identity. v2 adds the chart, and charts are
globally unique, which is what keeps those two apart.

stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from gat.corpus import (
    CHART_PREFIX,
    CORPUS_SCHEMA,
    LEGACY_CORPUS_SCHEMAS,
    CorpusError,
    load_corpus,
    validate_corpus_document,
)

_ROOT = Path(__file__).resolve().parents[1]
CORPUS = _ROOT / "validation" / "invariant-corpus-v2.json"
INDEX = _ROOT / "validation" / "invariant-corpus-index-v2.json"
SCHEMA = _ROOT / "validation" / "invariant-corpus.schema.json"


def _minimal(schema: str, *, chart: str | None) -> dict:
    coordinate: dict[str, object] = {"id": "var.thing", "quantity": "thing"}
    if chart is not None:
        coordinate["chart"] = chart
    return {
        "schema": schema,
        "claim_scope": "computational-integrity-only",
        "invariants": [{"id": "inv.one", "kind": "identity"}],
        "free_coordinates": [coordinate],
    }


class CorpusChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus()

    def test_canonical_corpus_is_v2_and_fully_charted(self) -> None:
        self.assertEqual(self.corpus.schema, CORPUS_SCHEMA)
        coordinates = self.corpus.free_coordinates
        self.assertTrue(coordinates)
        for row in coordinates:
            self.assertTrue(
                str(row.get("chart", "")).startswith(CHART_PREFIX),
                f"{row.get('id')} has no chart",
            )
        self.assertEqual(
            self.corpus.chart_of("var.opening-width"), "chart.cse-ifc-space"
        )

    def test_v2_without_a_chart_is_refused(self) -> None:
        with self.assertRaisesRegex(CorpusError, "chart"):
            validate_corpus_document(_minimal(CORPUS_SCHEMA, chart=None))

    def test_v2_chart_must_be_namespaced(self) -> None:
        with self.assertRaisesRegex(CorpusError, "chart"):
            validate_corpus_document(_minimal(CORPUS_SCHEMA, chart="plant"))

    def test_v1_still_loads_so_siblings_can_migrate_independently(self) -> None:
        for legacy in LEGACY_CORPUS_SCHEMAS:
            document = validate_corpus_document(_minimal(legacy, chart=None))
            self.assertEqual(document["schema"], legacy)

    def test_a_legacy_corpus_refuses_to_guess_a_chart(self) -> None:
        # Guessing is the conflation the field exists to stop.
        from gat.corpus import Corpus

        legacy = Corpus(
            _minimal(LEGACY_CORPUS_SCHEMAS[0], chart=None), Path("legacy.json")
        )
        self.assertEqual(legacy.charts(), {})
        with self.assertRaisesRegex(CorpusError, "declares no chart"):
            legacy.chart_of("var.thing")

    def test_unknown_schema_is_still_refused(self) -> None:
        with self.assertRaises(CorpusError):
            validate_corpus_document(_minimal("invariant-corpus-v9", chart="chart.x"))

    def test_published_schema_file_requires_the_chart(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema"]["const"], CORPUS_SCHEMA)
        items = schema["properties"]["free_coordinates"]["items"]
        self.assertIn("chart", items["required"])


class CorpusIndexChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = json.loads(INDEX.read_text(encoding="utf-8"))

    def test_every_needle_carries_a_chart(self) -> None:
        for row in self.index["members"]:
            charts = row.get("charts")
            self.assertIsInstance(charts, dict, f"{row['repo']} has no charts")
            for needle in row["needles"]:
                self.assertIn(needle, charts, f"{row['repo']}:{needle}")
                self.assertTrue(charts[needle].startswith(CHART_PREFIX))

    def test_charts_are_globally_unique(self) -> None:
        owner: dict[str, str] = {}
        for row in self.index["members"]:
            for chart in row["charts"].values():
                self.assertNotIn(
                    chart,
                    owner,
                    f"{chart} claimed by {owner.get(chart)} and {row['repo']}",
                )
                owner[chart] = row["repo"]
        self.assertEqual(len(owner), len(self.index["members"]))

    def test_the_var_x_collision_stays_disambiguated(self) -> None:
        # The regression this version exists for. Both members keep var.x;
        # what must never collapse is their charts.
        charts = {
            row["repo"]: row["charts"]["var.x"]
            for row in self.index["members"]
            if "var.x" in row["needles"]
        }
        self.assertEqual(
            charts,
            {
                "Parameterized-Lyapunov-Stability-Runtime": "chart.plsr-plant",
                "State-Estimation-Testbed": "chart.set-observation",
            },
        )
        self.assertEqual(len(set(charts.values())), 2)

    def test_index_states_that_a_needle_needs_its_chart(self) -> None:
        self.assertEqual(self.index["schema"], "invariant-corpus-index-v2")
        self.assertIn("chart", self.index["rule"])
        self.assertIn("globally unique", self.index["chart_rule"])

    def test_canonical_member_matches_the_local_corpus(self) -> None:
        canonical = self.index["canonical"]
        rows = [r for r in self.index["members"] if canonical.endswith(r["repo"])]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "canonical")
        self.assertEqual(rows[0]["charts"], load_corpus().charts())


class CorpusMigrationScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "migrate_corpus_v2", _ROOT / "validation" / "migrate_corpus_v2.py"
        )
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_migration_inserts_the_chart_next_to_the_id(self) -> None:
        legacy = _minimal(LEGACY_CORPUS_SCHEMAS[0], chart=None)
        out = self.script.migrate(legacy, "chart.test-frame")
        self.assertEqual(out["schema"], CORPUS_SCHEMA)
        row = out["free_coordinates"][0]
        self.assertEqual(list(row)[:2], ["id", "chart"])
        self.assertEqual(row["chart"], "chart.test-frame")
        # and the result is a document this repo would accept
        validate_corpus_document(out)

    def test_migration_charts_every_coordinate(self) -> None:
        legacy = _minimal(LEGACY_CORPUS_SCHEMAS[0], chart=None)
        legacy["free_coordinates"].append({"id": "var.other", "quantity": "other"})
        out = self.script.migrate(legacy, "chart.test-frame")
        self.assertEqual(
            [r["chart"] for r in out["free_coordinates"]],
            ["chart.test-frame", "chart.test-frame"],
        )

    def test_script_knows_every_chart_the_index_claims(self) -> None:
        claimed = self.script.claimed_charts()
        self.assertEqual(len(claimed), len(self.script.json.loads(INDEX.read_text())["members"]))
        self.assertEqual(claimed["chart.plsr-plant"], "Parameterized-Lyapunov-Stability-Runtime")
        self.assertEqual(claimed["chart.set-observation"], "State-Estimation-Testbed")


if __name__ == "__main__":
    unittest.main()
