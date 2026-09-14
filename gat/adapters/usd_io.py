"""Legacy zero-dependency USDA state-space interchange proof.

This closed, hand-emitted subset is retained as a NumPy-only fallback and an
executable portability proof. New carrier capabilities belong in
``gat.adapters.openusd``; JSON snapshots and that native OpenUSD adapter are
the canonical restart paths.

Not "USD export": the goal is that a *computational world* crosses the
boundary —

    S_A --encode--> USD stage --decode--> S_B,   S_A ~= S_B

under an explicit invariant suite, with enough structure preserved that a
receiving CSE runtime can *continue the computation* (apply further
transformations, recompute Jacobians, propagate uncertainty, verify).

Encoding layout (text USDA, hand-emitted like the SPF adapter — the
runtime dependency stays numpy-only):

* Real ``Xform``/``Cube`` prims carry the building's display geometry, so
  any stock USD tool opens the stage as a scene.  This geometry is a
  *derived view* (means of the state variables at export time); the
  decoder never reads it.
* Per-entity custom data (``gat_entity``) carries identity, semantics,
  placement, and every quantity slot — priors, roles, units, and the
  defining expression trees of derived quantities.  Expressions travel as
  definitions, so runtime B recomputes Jacobians instead of trusting
  serialized derivatives (transformation semantics survive, not just
  numbers).
* Layer custom data (``gat_state``) carries the joint Gaussian belief
  (variable order, mu, Sigma — floats serialized by shortest
  round-tripping repr, hence *bitwise* reconstruction), the relationship
  graph, the typed constraints, representation metadata, and the
  execution trace (provenance).

The stage commits to what it contains.  ``gat_state`` carries a module
digest, a bytewise world digest, a configuration digest, and a carrier digest
over the provenance the world identity deliberately excludes -- the source
path and the execution trace -- and ``load_usd`` recomputes all four against
the reconstruction and refuses a stage that does not answer for its own
contents.  Without that the carrier
is a text file with a decorative hash: a hand-edited storey height loaded
clean and ``gat verify`` reported a pass.  The three digests break in
distinguishable ways, so a refusal names which one did.

``state_equivalence`` is the invariant suite: identity, geometry,
topology, semantics, Gaussian state, constraints, provenance, and
configuration identity — each checked separately and reported, so
"the state survived" is a measured claim, not a vibe.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
import hashlib

import numpy as np

from typing import Mapping

from gat.engine.configuration import QUANT, configuration_digest
from gat.engine.executor import World
from gat.engine.verify import run_invariants
from gat.errors import SnapshotError, SpfParseError
from gat.gaussian.state import GaussianState
from gat.ids import EntityId, VarId
from gat.ir.core import (
    Entity,
    ExprEquals,
    LessEqual,
    Module,
    NonNegative,
    Placement,
    QtySlot,
    Rel,
    RelKind,
    Role,
    Unit,
)
from gat.ir.exprs import expr_from_obj, expr_to_obj

FORMAT = "gat-usd v1"

#: Carriers written before the commitment was checked on load.  They are
#: refused by version rather than by digest, because a v0 stage predates the
#: path-independent world identity and would fail for two reasons at once.
LEGACY_FORMATS = frozenset({"gat-usd v0"})


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def carrier_digest(meta: Mapping[str, object], trace: list) -> str:
    """Commit to what the carrier carries but the world identity does not.

    ``meta["source"]`` is deliberately outside the module digest -- a world is
    named by its model's bytes, not by the caller's path (see
    ``docs/world-identity-v2.md``) -- and the execution trace is provenance,
    not state.  Both travel in the stage anyway, so without this a carrier
    could be edited to name ``/approved/CERTIFIED-final.ifc`` as its source and
    carry a fabricated "signed off by engineer" event, and still verify clean:
    every number it commits to is untouched.  Nothing downstream reads that
    trace today, which was equally true of ``world_digest`` before it was
    checked.
    """
    payload = json.dumps(
        {"meta": dict(meta), "trace": trace}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _usda_string(payload: str) -> str:
    """Encode a payload as a single-quoted USDA string literal."""
    return "'" + payload.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _var_triple(var: VarId) -> list:
    return [var.entity.ifc_class, var.entity.global_id, var.quantity]


def _var_from_triple(obj: list) -> VarId:
    return VarId(EntityId(str(obj[0]), str(obj[1])), str(obj[2]))


def _entity_record(world: World, entity: Entity) -> dict:
    slots = []
    for qname in sorted(entity.slots):
        slot = entity.slots[qname]
        slots.append(
            {
                "q": qname,
                "role": slot.role.value,
                "unit": slot.unit.value,
                "prior_mu": slot.prior_mu,
                "prior_sigma": slot.prior_sigma,
                "source_ref": slot.source_ref,
                "expr": expr_to_obj(slot.expr) if slot.expr is not None else None,
            }
        )
    record = {
        "ifc_class": entity.id.ifc_class,
        "global_id": entity.id.global_id,
        "name": entity.name,
        "attrs": {k: entity.attrs[k] for k in sorted(entity.attrs)},
        "source_ref": entity.source_ref,
        "slots": slots,
    }
    if entity.placement is not None:
        p = entity.placement
        record["placement"] = {"x": p.x, "y": p.y, "z": p.z, "angle": p.angle}
    return record


def _constraint_obj(c) -> list:
    if isinstance(c, NonNegative):
        return ["nonneg", _var_triple(c.var), c.tol]
    if isinstance(c, LessEqual):
        return ["lesseq", _var_triple(c.lhs), _var_triple(c.rhs), c.tol]
    if isinstance(c, ExprEquals):
        return ["expreq", _var_triple(c.var), expr_to_obj(c.expr), c.tol]
    raise TypeError(f"unknown constraint {type(c).__name__}")


def _constraint_from_obj(obj: list):
    tag = obj[0]
    if tag == "nonneg":
        return NonNegative(_var_from_triple(obj[1]), float(obj[2]))
    if tag == "lesseq":
        return LessEqual(_var_from_triple(obj[1]), _var_from_triple(obj[2]), float(obj[3]))
    if tag == "expreq":
        return ExprEquals(_var_from_triple(obj[1]), expr_from_obj(obj[2]), float(obj[3]))
    raise ValueError(f"unknown constraint tag {tag!r}")


#: Display-box extent quantities per class (derived view only).
_DISPLAY_EXTENTS: dict[str, tuple[str, str, str] | None] = {
    "IfcWall": ("Length", "Width", "Height"),
    "IfcSpace": ("Length", "Width", None),  # z filled from the storey below
    "IfcDoor": ("Width", None, "Height"),
}


def _display_extents(world: World, entity: Entity) -> tuple[float, float, float] | None:
    spec = _DISPLAY_EXTENTS.get(entity.id.ifc_class)
    if spec is None:
        return None
    storeys = [e for e in world.module.entities if e.ifc_class == "IfcBuildingStorey"]
    values = []
    for axis, qname in enumerate(spec):
        if qname is not None and qname in entity.slots:
            values.append(world.full.mean(entity.var(qname)))
        elif entity.id.ifc_class == "IfcSpace" and axis == 2 and storeys:
            values.append(world.full.mean(VarId(storeys[0], "ClearHeight")))
        elif entity.id.ifc_class == "IfcDoor" and axis == 1:
            values.append(0.05)
        else:
            return None
    return (values[0], values[1], values[2])


def export_usd(world: World, path: str, trace_events: list | None = None) -> int:
    """Write the world as a USD stage; returns the entity count."""
    module = world.module

    state = {
        "format": FORMAT,
        "meta": dict(module.meta),
        "n_raw": world.binding.n_raw,
        "var_order": [_var_triple(v) for v in world.binding.raw_index.vars],
        "mu": [float(x) for x in world.belief.mu],
        "sigma": [[float(x) for x in row] for row in world.belief.sigma],
        "rels": [
            [
                rel.kind.value,
                rel.source.ifc_class,
                rel.source.global_id,
                rel.target.ifc_class,
                rel.target.global_id,
            ]
            for rel in module.rels
        ],
        "constraints": [_constraint_obj(c) for c in module.constraints],
        "trace": trace_events or [],
        "module_digest": module.digest(),
        "carrier_digest": carrier_digest(module.meta, trace_events or []),
        "world_digest": world.digest(),
        "configuration_digest": configuration_digest(world),
    }

    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "Building"',
        "    metersPerUnit = 1",
        '    upAxis = "Z"',
        "    customLayerData = {",
        f"        string gat_format = {_usda_string(FORMAT)}",
        f"        string gat_state = {_usda_string(json.dumps(state, sort_keys=True))}",
        "    }",
        ")",
        "",
        'def Xform "Building"',
        "{",
    ]

    for k, eid in enumerate(module.entities):
        entity = module.entities[eid]
        record = json.dumps(_entity_record(world, entity), sort_keys=True)
        prim = f"E{k}_{eid.global_id}"
        lines.append(f'    def Xform "{prim}" (')
        lines.append("        customData = {")
        lines.append(f"            string gat_entity = {_usda_string(record)}")
        lines.append("        }")
        lines.append("    )")
        lines.append("    {")
        if entity.placement is not None:
            p = entity.placement
            lines.append(
                f"        double3 xformOp:translate = ({p.x!r}, {p.y!r}, {p.z!r})"
            )
            lines.append(
                f"        double xformOp:rotateZ = {math.degrees(p.angle)!r}"
            )
            lines.append(
                '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateZ"]'
            )
        extents = _display_extents(world, entity)
        if extents is not None:
            ex, ey, ez = extents
            lines.append('        def Cube "Geom"')
            lines.append("        {")
            lines.append("            double size = 1")
            lines.append(
                f"            double3 xformOp:translate = ({ex/2!r}, {ey/2!r}, {ez/2!r})"
            )
            lines.append(
                f"            double3 xformOp:scale = ({ex!r}, {ey!r}, {ez!r})"
            )
            lines.append(
                '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]'
            )
            lines.append("        }")
        lines.append("    }")
    lines.append("}")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(module.entities)


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def _extract_strings(text: str, marker: str) -> list[str]:
    """Extract every single-quoted USDA string assigned to ``marker``."""
    out = []
    pos = 0
    needle = f"{marker} = '"
    while True:
        start = text.find(needle, pos)
        if start < 0:
            return out
        i = start + len(needle)
        buf = []
        while True:
            if i >= len(text):
                raise SpfParseError(f"unterminated {marker} string in USD layer")
            ch = text[i]
            if ch == "\\":
                if i + 1 >= len(text):
                    raise SpfParseError(f"bad escape in {marker} string")
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                break
            buf.append(ch)
            i += 1
        out.append("".join(buf))
        pos = i + 1


#: The three commitments a carrier must answer for on load.  They settle
#: different questions — the transferred IR, the belief bytewise, and the
#: architectural configuration to within ``QUANT`` — so which one breaks says
#: what was done to the stage.  Ordered narrowest cause first.
_COMMITMENTS = (
    "module_digest",
    "world_digest",
    "configuration_digest",
    "carrier_digest",
)


def _recorded_commitments(state: dict) -> dict[str, str]:
    recorded = {}
    for key in _COMMITMENTS:
        value = state.get(key)
        if not isinstance(value, str) or not value:
            raise SnapshotError(
                f"carrier records no {key}: there is nothing to check its "
                "contents against, so it cannot be loaded"
            )
        recorded[key] = value
    return recorded


def _check_commitments(
    world: World, recorded: dict[str, str], trace: list
) -> None:
    """Refuse a carrier whose contents are not what it commits to.

    The stage is a text file, and nothing stops an editor from changing a
    mean in it.  Until this check existed nothing did: a hand-edited storey
    height loaded clean and ``gat verify`` reported twelve passes.  The three
    digests fail in distinguishable ways, so the refusal names which one
    broke rather than reporting a generic mismatch.
    """
    verification = run_invariants(world)
    if not verification.passed:
        broken = ", ".join(result.invariant_id for result in verification.failures)
        raise SnapshotError(f"carrier world fails its own invariants: {broken}")

    computed = {
        "module_digest": world.module.digest(),
        "world_digest": world.digest(),
        "configuration_digest": configuration_digest(world),
        "carrier_digest": carrier_digest(world.module.meta, trace),
    }
    broken = [key for key in _COMMITMENTS if computed[key] != recorded[key]]
    if not broken:
        return

    if "module_digest" in broken:
        cause = "the transferred IR is not the IR this carrier was written from"
    elif "configuration_digest" in broken:
        cause = (
            "the architectural configuration in this stage is not the one it "
            "commits to; a quantity was altered after export"
        )
    elif broken == ["carrier_digest"]:
        cause = (
            "the state is intact but the provenance around it is not: this "
            "stage's source or execution trace was edited after export"
        )
    else:
        # Configuration identity quantizes to QUANT and reads means and sigmas
        # only, so it can agree while the raw belief does not.  Both readings
        # are stated because this runtime cannot tell them apart from here.
        cause = (
            "the architectural configuration still matches but the belief does "
            f"not reproduce bytewise: either an edit below {QUANT:g}, or a "
            "runtime whose numeric configuration differs from the exporting one"
        )
    detail = ", ".join(
        f"{key} {recorded[key][:16]} -> {computed[key][:16]}" for key in broken
    )
    raise SnapshotError(f"carrier refused: {cause} [{detail}]")


def load_usd(path: str) -> tuple[World, list]:
    """Reconstruct a world from a CSE USD stage.

    Returns ``(world, imported_trace_events)``.  The belief is restored
    bitwise (repr-round-tripped floats); the dependency DAG, Jacobian
    machinery, and invariants are recompiled from the transferred
    definitions.  The reconstruction is then checked against the three
    digests the carrier commits to, and a stage that does not answer for its
    own contents is refused rather than loaded.
    """
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    states = _extract_strings(text, "gat_state")
    if len(states) != 1:
        raise SpfParseError(f"expected exactly one gat_state block, found {len(states)}")
    state = json.loads(states[0])
    declared = state.get("format")
    layer_formats = _extract_strings(text, "gat_format")
    if layer_formats != [declared]:
        # The layer declares the format for any USD tool that opens the stage;
        # the state block declares it for this decoder. A stage where they
        # disagree is telling two stories about what it is.
        raise SpfParseError(
            f"stage declares format {layer_formats!r} to a reader and "
            f"{declared!r} to this decoder"
        )
    if declared in LEGACY_FORMATS:
        raise SpfParseError(
            f"carrier format {declared!r} predates the checked commitment and "
            f"the path-independent world identity; re-export it as {FORMAT}"
        )
    if declared != FORMAT:
        raise SpfParseError(f"unsupported gat-usd format {declared!r}")
    recorded = _recorded_commitments(state)

    entities: dict[EntityId, Entity] = {}
    for record_text in _extract_strings(text, "gat_entity"):
        record = json.loads(record_text)
        eid = EntityId(record["ifc_class"], record["global_id"])
        slots: dict[str, QtySlot] = {}
        for s in record["slots"]:
            slots[s["q"]] = QtySlot(
                var=VarId(eid, s["q"]),
                role=Role(s["role"]),
                unit=Unit(s["unit"]),
                prior_mu=float(s["prior_mu"]),
                prior_sigma=float(s["prior_sigma"]),
                expr=expr_from_obj(s["expr"]) if s["expr"] is not None else None,
                source_ref=s["source_ref"],
            )
        placement = None
        if "placement" in record:
            p = record["placement"]
            placement = Placement(p["x"], p["y"], p["z"], p["angle"])
        entities[eid] = Entity(
            id=eid,
            name=record["name"],
            attrs=record["attrs"],
            slots=slots,
            placement=placement,
            source_ref=record["source_ref"],
        )

    rels = tuple(
        Rel(
            RelKind(r[0]),
            EntityId(str(r[1]), str(r[2])),
            EntityId(str(r[3]), str(r[4])),
        )
        for r in state["rels"]
    )
    constraints = tuple(_constraint_from_obj(c) for c in state["constraints"])
    module = Module(
        entities=entities,
        rels=rels,
        constraints=constraints,
        meta=dict(state["meta"]),
    )

    try:
        world = World.compile(module)
    except Exception as exc:
        raise SnapshotError(f"carrier IR could not be compiled: {exc}") from exc

    # Restore the belief bitwise, permuting the serialized order into the
    # fresh binding's canonical order (they normally coincide).
    serialized_order = [_var_from_triple(t) for t in state["var_order"]]
    carried = set(serialized_order)
    missing = [v for v in world.binding.raw_index.vars if v not in carried]
    if missing:
        raise SnapshotError(
            f"carrier belief covers {len(serialized_order)} variables but the "
            f"compiled IR binds {world.binding.n_raw}; {missing[0]} has no "
            "serialized row"
        )
    row_of = {var: row for row, var in enumerate(serialized_order)}
    perm = [row_of[v] for v in world.binding.raw_index.vars]
    try:
        mu = np.array([state["mu"][i] for i in perm], dtype=np.float64)
        sigma = np.array(state["sigma"], dtype=np.float64)[np.ix_(perm, perm)]
        world = world.with_belief(GaussianState(world.binding.raw_index, mu, sigma))
    except Exception as exc:
        raise SnapshotError(f"carrier belief could not be restored: {exc}") from exc

    trace = list(state.get("trace", []))
    _check_commitments(world, recorded, trace)
    return world, trace


# ---------------------------------------------------------------------------
# The invariant suite
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvariantCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EquivalenceReport:
    checks: tuple[InvariantCheck, ...]

    @property
    def equivalent(self) -> bool:
        return all(c.passed for c in self.checks)

    def render(self) -> str:
        lines = []
        for c in self.checks:
            lines.append(f"  {'PASS' if c.passed else 'FAIL'}  I_{c.name:<13} {c.detail}")
        verdict = "EQUIVALENT" if self.equivalent else "NOT EQUIVALENT"
        return "\n".join(lines + [f"  -> {verdict}"])


def state_equivalence(a: World, b: World) -> EquivalenceReport:
    """The formal invariant suite: D(E(S)) ~= S, made testable."""
    checks: list[InvariantCheck] = []

    ids_a = {(e, a.module.entities[e].name) for e in a.module.entities}
    ids_b = {(e, b.module.entities[e].name) for e in b.module.entities}
    checks.append(
        InvariantCheck("identity", ids_a == ids_b, f"{len(ids_a)} entities, names and ids")
    )

    geo_ok = True
    for eid in a.module.entities:
        pa = a.module.entities[eid].placement
        pb = b.module.entities.get(eid) and b.module.entities[eid].placement
        if (pa is None) != (pb is None) or (pa is not None and pa != pb):
            geo_ok = False
            break
    checks.append(InvariantCheck("geometry", geo_ok, "placements exact"))

    rels_ok = set(a.module.rels) == set(b.module.rels)
    checks.append(
        InvariantCheck("topology", rels_ok, f"{len(a.module.rels)} relationship edges")
    )

    sem_ok = all(
        dict(a.module.entities[e].attrs) == dict(b.module.entities[e].attrs)
        for e in a.module.entities
        if e in b.module.entities
    )
    checks.append(InvariantCheck("semantics", sem_ok, "classes and attributes"))

    gauss_ok = (
        a.binding.raw_index.vars == b.binding.raw_index.vars
        and a.belief.mu.tobytes() == b.belief.mu.tobytes()
        and a.belief.sigma.tobytes() == b.belief.sigma.tobytes()
    )
    max_diff = (
        float(np.abs(a.belief.sigma - b.belief.sigma).max())
        if a.belief.sigma.shape == b.belief.sigma.shape
        else float("inf")
    )
    checks.append(
        InvariantCheck(
            "gaussian", gauss_ok, f"mu and Sigma bitwise (max |dSigma| = {max_diff:.1e})"
        )
    )

    cons_ok = {json.dumps(_constraint_obj(c)) for c in a.module.constraints} == {
        json.dumps(_constraint_obj(c)) for c in b.module.constraints
    }
    checks.append(
        InvariantCheck("constraints", cons_ok, f"{len(a.module.constraints)} typed constraints")
    )

    prov_ok = dict(a.module.meta) == dict(b.module.meta)
    checks.append(InvariantCheck("provenance", prov_ok, "representation metadata"))

    config_ok = configuration_digest(a) == configuration_digest(b)
    checks.append(
        InvariantCheck("configuration", config_ok, "moduli-quotient identity digest")
    )

    return EquivalenceReport(tuple(checks))
