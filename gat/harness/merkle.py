"""Sorted SHA-256 Merkle tree over record digests.

Satellite. Inclusion only. Not a ledger replacement. Not a guest.
Odd leftover is hashed with itself. A single leaf is the root.
An empty set hashes the empty JSON array.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Sequence

from gat.adapters.external_commitment import canonical_digest

_HEX = 64


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pair(left: str, right: str) -> str:
    return _sha256_hex(bytes.fromhex(left) + bytes.fromhex(right))


def merkle_leaves(digests: Iterable[str]) -> tuple[str, ...]:
    leaves: list[str] = []
    for item in digests:
        if not isinstance(item, str) or len(item) != _HEX:
            raise ValueError("merkle leaf must be a 64-char sha256 hex digest")
        try:
            bytes.fromhex(item)
        except ValueError as exc:
            raise ValueError("merkle leaf must be lowercase hex") from exc
        if item != item.lower():
            raise ValueError("merkle leaf must be lowercase hex")
        leaves.append(item)
    return tuple(sorted(set(leaves)))


def merkle_root(digests: Iterable[str]) -> str:
    leaves = merkle_leaves(digests)
    if not leaves:
        return canonical_digest([])
    layer = list(leaves)
    while len(layer) > 1:
        nxt: list[str] = []
        for index in range(0, len(layer), 2):
            left = layer[index]
            right = layer[index] if index + 1 == len(layer) else layer[index + 1]
            nxt.append(_pair(left, right))
        layer = nxt
    return layer[0]


def merkle_proof(digests: Iterable[str], leaf: str) -> list[dict[str, str]]:
    leaves = merkle_leaves(digests)
    if leaf not in leaves:
        raise ValueError("leaf is not in the committed set")
    if len(leaves) <= 1:
        return []
    layer = list(leaves)
    index = layer.index(leaf)
    path: list[dict[str, str]] = []
    while len(layer) > 1:
        if index % 2 == 0:
            sibling_index = index if index + 1 == len(layer) else index + 1
            side = "right"
        else:
            sibling_index = index - 1
            side = "left"
        path.append({"side": side, "digest": layer[sibling_index]})
        nxt: list[str] = []
        for cursor in range(0, len(layer), 2):
            left = layer[cursor]
            right = layer[cursor] if cursor + 1 == len(layer) else layer[cursor + 1]
            nxt.append(_pair(left, right))
        layer = nxt
        index //= 2
    return path


def verify_merkle_proof(
    leaf: str, path: Sequence[Mapping[str, object]], root: str
) -> bool:
    current = leaf
    for step in path:
        sibling = str(step["digest"])
        if step["side"] == "left":
            current = _pair(sibling, current)
        elif step["side"] == "right":
            current = _pair(current, sibling)
        else:
            raise ValueError("path side must be left or right")
    return current == root
