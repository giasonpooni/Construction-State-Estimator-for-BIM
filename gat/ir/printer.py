"""Deterministic textual dump of the Architectural IR.

The printer output is byte-stable for a given module: entities, slots,
relationships, and constraints are emitted in their canonical sorted
orders with fixed float formatting.  The module digest is the SHA-256 of
this text.

Identity is deliberately narrower than metadata.  Keys in
:data:`PROVENANCE_META` describe how a module was obtained and never enter
the digest; everything else does.  That is what makes a world digest a
statement about *the model*, not about the caller's working directory.

"Everything else" includes each constraint's ``tol``.  It did not until
``gat-ir v2``: the text named a constraint's variables and its shape and
stopped, so two modules whose only difference was a tolerance of 1e-09
against one of 1e9 printed the same bytes and carried the same module,
world, and configuration digest.  A tolerance is not a presentation detail
-- it is the whole quantitative content of ``CONS-01``, ``CONS-02`` and
``CONS-03``.  Measured on ``gat/demo/model.ifc``: rewriting every ``tol`` in
an exported snapshot and recomputing the envelope's own unkeyed SHA-256
produced a state that loads clean, reports digest
``793474ab...`` -- byte-identical to the honest one -- and then *accepts* a
door driven a metre past its opening, where the honest world refuses it with
``VerificationError: CONS-02``.  Anything bound to a world digest, including
an evidence receipt's ``result_world_digest``, was bound to both worlds at
once.
"""

from __future__ import annotations

from gat.ir.core import (
    ExprEquals,
    LessEqual,
    Module,
    NonNegative,
    Role,
)


#: Meta keys that record *where a module came from* rather than *what it
#: is*.  They are kept for humans and deliberately excluded from the digest
#: text, so the same bytes lowered through a different path — a relative
#: path, an absolute one, a basename — keep one identity.  Identity instead
#: rides on ``source_sha256``, the digest of the source bytes themselves.
PROVENANCE_META: frozenset[str] = frozenset({"source"})


def _fmt(value: float) -> str:
    return repr(float(value))


def print_module(module: Module) -> str:
    lines: list[str] = ["gat-ir v2"]
    for key in sorted(module.meta):
        if key in PROVENANCE_META:
            continue
        lines.append(f"meta {key} = {module.meta[key]}")

    for eid in module.entities:
        entity = module.entities[eid]
        lines.append(f"entity {eid} name={entity.name!r}")
        if entity.placement is not None:
            p = entity.placement
            lines.append(
                f"  placement x={_fmt(p.x)} y={_fmt(p.y)} z={_fmt(p.z)} angle={_fmt(p.angle)}"
            )
        for akey in sorted(entity.attrs):
            lines.append(f"  attr {akey} = {entity.attrs[akey]!r}")
        for qname in sorted(entity.slots):
            slot = entity.slots[qname]
            if slot.role is Role.RAW:
                lines.append(
                    f"  raw {qname} : {slot.unit.value} "
                    f"~ N({_fmt(slot.prior_mu)}, {_fmt(slot.prior_sigma)}^2)"
                )
            else:
                assert slot.expr is not None
                lines.append(
                    f"  derived {qname} : {slot.unit.value} := {slot.expr.to_str()}"
                )

    for rel in module.rels:
        lines.append(f"rel {rel.kind.value} {rel.source} -> {rel.target}")

    for c in module.constraints:
        # ``tol`` is emitted unconditionally, including when it equals the
        # dataclass default. Omitting the default would keep the digests of
        # every existing module unchanged and would still be lossless today,
        # but it would silently tie identity to a constant in
        # ``gat.ir.core``: change that default and two modules written under
        # the two values collide. The cost of saying it every time is one
        # short suffix per constraint.
        if isinstance(c, NonNegative):
            lines.append(f"constraint nonneg {c.var} tol={_fmt(c.tol)}")
        elif isinstance(c, LessEqual):
            lines.append(
                f"constraint lesseq {c.lhs} <= {c.rhs} tol={_fmt(c.tol)}"
            )
        elif isinstance(c, ExprEquals):
            lines.append(
                f"constraint expreq {c.var} == {c.expr.to_str()} "
                f"tol={_fmt(c.tol)}"
            )

    return "\n".join(lines) + "\n"
