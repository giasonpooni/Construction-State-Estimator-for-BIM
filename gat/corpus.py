"""Invariant reference corpus.

I is declared identity. Inference may only needle names that already sit in I.

v2 adds ``chart`` to every free coordinate. A needle names a quantity that is
free until a declaration fixes it; the chart names the coordinate system that
declaration fixes it *in*. Without it a needle id is ambiguous across the
portfolio: PLSR and the State-Estimation-Testbed both declare ``var.x`` with
quantity ``state``, but one is fixed by a declared plant A and the other by a
declared observation H, so they are not the same coordinate and a covariance
on one may not be read as a covariance on the other.

v1 documents still load, so sibling corpora can migrate independently, but
they carry no chart and nothing may assume one.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from gat.artifact_paths import validation_artifact

CORPUS_SCHEMA = "invariant-corpus-v2"
LEGACY_CORPUS_SCHEMAS = ("invariant-corpus-v1",)
CHART_PREFIX = "chart."
CLAIM_SCOPE = "computational-integrity-only"
CORPUS_FILE = "invariant-corpus-v2.json"


class CorpusError(ValueError):
    """Name is not in the corpus. Inference must not invent it."""


def validate_corpus_document(document: Mapping[str, object]) -> dict[str, object]:
    schema = document.get("schema")
    if schema != CORPUS_SCHEMA and schema not in LEGACY_CORPUS_SCHEMAS:
        accepted = ", ".join((CORPUS_SCHEMA,) + LEGACY_CORPUS_SCHEMAS)
        raise CorpusError(f"schema must be one of {accepted}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise CorpusError("corpus claim_scope must stay computational-integrity-only")
    invariants = document.get("invariants")
    free = document.get("free_coordinates")
    if not isinstance(invariants, list) or not invariants:
        raise CorpusError("corpus needs at least one invariant")
    if not isinstance(free, list) or not free:
        raise CorpusError("corpus needs at least one free coordinate")
    seen: set[str] = set()
    for row in list(invariants) + list(free):
        if not isinstance(row, dict):
            raise CorpusError("corpus rows must be objects")
        ident = row.get("id")
        if not isinstance(ident, str) or not ident:
            raise CorpusError("corpus row needs an id")
        if ident in seen:
            raise CorpusError(f"duplicate corpus id {ident!r}")
        seen.add(ident)
    if not any(isinstance(row, dict) and str(row.get("id", "")).startswith("var.") for row in free):
        raise CorpusError("free_coordinates must include a var.* needle")
    if schema == CORPUS_SCHEMA:
        for row in free:
            chart = row.get("chart")
            if not isinstance(chart, str) or not chart.startswith(CHART_PREFIX):
                raise CorpusError(
                    f"free coordinate {row.get('id')!r} needs a "
                    f"{CHART_PREFIX}* chart naming the coordinate system its "
                    "declaration fixes it in"
                )
    return dict(document)


@dataclass(frozen=True)
class Corpus:
    document: dict[str, object]
    path: Path

    @property
    def invariants(self) -> tuple[dict[str, object], ...]:
        rows = self.document.get("invariants")
        if not isinstance(rows, list):
            raise CorpusError("corpus invariants must be an array")
        return tuple(row for row in rows if isinstance(row, dict))

    @property
    def free_coordinates(self) -> tuple[dict[str, object], ...]:
        rows = self.document.get("free_coordinates")
        if rows is None:
            return ()
        if not isinstance(rows, list):
            raise CorpusError("free_coordinates must be an array")
        return tuple(row for row in rows if isinstance(row, dict))

    def ids(self) -> frozenset[str]:
        names = []
        for row in self.invariants + self.free_coordinates:
            ident = row.get("id")
            if isinstance(ident, str):
                names.append(ident)
        return frozenset(names)

    def get(self, ident: str) -> dict[str, object]:
        for row in self.invariants + self.free_coordinates:
            if row.get("id") == ident:
                return dict(row)
        raise CorpusError(f"{ident!r} is not in the invariant corpus")

    def require(self, ident: str) -> dict[str, object]:
        return self.get(ident)

    def global_ids(self) -> frozenset[str]:
        found = []
        for row in self.invariants:
            guid = row.get("global_id")
            if isinstance(guid, str):
                found.append(guid)
        return frozenset(found)

    @property
    def schema(self) -> str:
        schema = self.document.get("schema")
        return schema if isinstance(schema, str) else ""

    def chart_of(self, ident: str) -> str:
        """The coordinate system ``ident`` is expressed in.

        Raises on a v1 corpus: a legacy document declares no chart, and
        guessing one is exactly the conflation this field exists to stop.
        """
        row = self.get(ident)
        chart = row.get("chart")
        if not isinstance(chart, str) or not chart:
            raise CorpusError(
                f"{ident!r} declares no chart; {self.path.name} is "
                f"{self.schema or 'unversioned'}, not {CORPUS_SCHEMA}"
            )
        return chart

    def charts(self) -> dict[str, str]:
        """Every free coordinate that declares a chart, needle -> chart."""
        found: dict[str, str] = {}
        for row in self.free_coordinates:
            ident, chart = row.get("id"), row.get("chart")
            if isinstance(ident, str) and isinstance(chart, str) and chart:
                found[ident] = chart
        return found

    def needle(self, ident: str) -> dict[str, object]:
        row = self.get(ident)
        if ident.startswith("var.") or row.get("quantity"):
            chart = row.get("chart")
            return {
                "coordinate": ident,
                "chart": chart if isinstance(chart, str) else None,
                "row": row,
                "in_corpus": True,
                "may_observe": True,
            }
        raise CorpusError(f"{ident!r} is an invariant, not a free coordinate")


def load_corpus(path: str | Path | None = None) -> Corpus:
    target = Path(path) if path is not None else validation_artifact(CORPUS_FILE)
    document = validate_corpus_document(json.loads(target.read_text(encoding="utf-8")))
    return Corpus(document, target)


def refuse_unknown(ident: str, corpus: Corpus | None = None) -> None:
    table = corpus or load_corpus()
    table.require(ident)
