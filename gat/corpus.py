"""Invariant reference corpus.

I is declared identity. Inference may only needle names that already sit in I.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

CORPUS_SCHEMA = "invariant-corpus-v1"
CLAIM_SCOPE = "computational-integrity-only"
_DEFAULT = Path(__file__).resolve().parents[1] / "validation" / "invariant-corpus-v1.json"


class CorpusError(ValueError):
    """Name is not in the corpus. Inference must not invent it."""


def validate_corpus_document(document: Mapping[str, object]) -> dict[str, object]:
    if document.get("schema") != CORPUS_SCHEMA:
        raise CorpusError("schema must be invariant-corpus-v1")
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

    def needle(self, ident: str) -> dict[str, object]:
        row = self.get(ident)
        if ident.startswith("var.") or row.get("quantity"):
            return {
                "coordinate": ident,
                "row": row,
                "in_corpus": True,
                "may_observe": True,
            }
        raise CorpusError(f"{ident!r} is an invariant, not a free coordinate")


def load_corpus(path: str | Path | None = None) -> Corpus:
    target = Path(path) if path is not None else _DEFAULT
    document = validate_corpus_document(json.loads(target.read_text(encoding="utf-8")))
    return Corpus(document, target)


def refuse_unknown(ident: str, corpus: Corpus | None = None) -> None:
    table = corpus or load_corpus()
    table.require(ident)
