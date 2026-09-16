"""Inspectability index: space-id readiness, not an inspection stamp.

Satellite. The fold lives in gat.harness.inspectability so the experiment
harness and this import stay one object.
"""

from gat.harness.inspectability import (
    INDEX_FORMAT,
    InspectabilityIndex,
    fold_inspectability,
    tickets_from_index,
)

__all__ = [
    "INDEX_FORMAT",
    "InspectabilityIndex",
    "fold_inspectability",
    "tickets_from_index",
]
