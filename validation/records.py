"""Build every shipped validation record from a live run.

This module is the single producer of the records in ``validation/``.
``regenerate.py`` writes what it returns; ``tests/test_validation_records.py``
re-runs it and fails if a shipped file has drifted. Because both go through
here, a record cannot be updated by hand without the test noticing.

The rule for what belongs in a record: it must be *reproducible*. Digests,
verdicts, dispositions, variable counts and derived quantities qualify.
Wall-clock timings do not, and are deliberately absent — the environment
sensitive scale numbers live in ``incremental-scale-reference-v1.json``,
which declares the host it was measured on and is not asserted here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import gat.demo
from gat.adapters.ifc.beam_geometry import derive_beam_geometry
from gat.adapters.ifc.parser import parse_ifc_file
from gat.adapters.ifc.reader import global_id
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.engineering.beam import BeamBendingCheck, BeamBendingEvaluator
from gat.engineering.certificate_signature import (
    TEST_KEY_ID,
    sign_certificate_bytes,
    fixture_trust_store,
    verify_certificate_bytes,
)
from gat.engineering.material_certificate import read_material_certificate
from gat.engineering.section_corroboration import corroborate_beam_section
from gat.errors import GatError
from gat.gaussian.sparse_factors import inventory_sparse_factors
from gat.session import GatSession
from gat.workflows.geometry_authority import authority_from_beam_status
from gat.workflows import (
    AcceptanceCase,
    AcceptancePolicy,
    capacity_check,
    DifferenceDecision,
    WorkflowKind,
    assess_difference,
    difference_check,
    evaluate_acceptance_case,
)


DEMO = Path(gat.demo.__file__).parent
OFFICE_MODEL = DEMO / "model.ifc"
BEAM_MODEL = DEMO / "beam_model.ifc"
CERTIFICATE = DEMO / "material_certificate.json"

CLINIC_FILE = "buildingSMART-Clinic-Structural.ifc"
CLINIC_BEAM = "2Uhw1he2z3UO$DBmBugLyy"
WALL_OPENING_FILE = "buildingSMART-wall-opening-window.ifc"

BEAM_DEMAND_N_M = 301_000.0
BEAM_CONFIDENCE = 0.95

#: Records that can only be built with the fetched public IFC corpus. They
#: are shipped, but a host without the corpus neither rebuilds nor checks them.
CORPUS_DEPENDENT: frozenset[str] = frozenset(
    {"clinic-w460x60-scoped-world-v1.json", "corpus-inventory-v1.json"}
)


# -- opening fit -----------------------------------------------------------


def _opening_fit_case(session: GatSession) -> AcceptanceCase:
    checks = []
    for check_id, quantity in (("width", "Width"), ("height", "Height")):
        assessment = assess_difference(
            session.world,
            DifferenceDecision(
                session.var("Opening-1", quantity),
                session.var("Door-1", quantity),
                minimum_margin=0.05,
                confidence=0.95,
                label=f"Door-1 {quantity.lower()} fit",
            ),
        )
        checks.append(difference_check(check_id, assessment))
    return AcceptanceCase(
        "opening-fit-demo",
        WorkflowKind.OPENING_VERIFICATION,
        "Door-1 into Opening-1",
        tuple(checks),
    )


def build_opening_fit_records() -> dict[str, dict]:
    """The same case under two policies: as-built, and explicit design review."""
    session = GatSession.load_ifc(str(OFFICE_MODEL))
    case = _opening_fit_case(session)
    as_built = evaluate_acceptance_case(case)
    design_review = evaluate_acceptance_case(
        case,
        policy=AcceptancePolicy(
            "design-review-v1",
            require_verified_evidence_for_accept=False,
        ),
    )
    return {
        "opening-fit-disposition-v1.json": as_built.to_dict(),
        "opening-fit-design-review-disposition-v1.json": design_review.to_dict(),
    }


# -- beam certificate chain ------------------------------------------------


def _beam_chain() -> dict[str, object]:
    """Run Beam-B1 prior -> material certificate -> revised, once."""
    session = GatSession.load_ifc(str(BEAM_MODEL))
    beam = session.entity_by_name("Beam-B1")
    check = BeamBendingCheck(
        beam, BEAM_DEMAND_N_M, BEAM_CONFIDENCE, "Beam-B1 factored bending"
    )
    evaluator = BeamBendingEvaluator()

    prior = evaluator.evaluate(session.world, check)
    prior_world_digest = session.world.digest()

    evidence = read_material_certificate(CERTIFICATE).to_evidence(session.world)
    observation = evidence.observation
    transition = session.run(observation.transformation(session.world))
    revised = evaluator.evaluate(
        session.world,
        check,
        changed_inputs=transition.targets,
        affected_variables=transition.affected,
    )
    return {
        "beam": beam,
        "prior": prior,
        "revised": revised,
        "prior_world_digest": prior_world_digest,
        "result_world_digest": session.world.digest(),
        "session": session,
    }


def _beam_support(session: GatSession, beam) -> dict[str, object]:
    """What actually backs the shipped beam's section modulus.

    The model carries a W360X57 swept solid, so the adapter derives the
    elastic modulus S from the profile independently of the declared plastic
    modulus Z. The support block records both halves: what the geometry says
    on its own, and whether it corroborates the declaration.
    """
    digest = hashlib.sha256(BEAM_MODEL.read_bytes()).hexdigest()
    file = parse_ifc_file(str(BEAM_MODEL))
    instance = next(
        candidate
        for candidate in file.by_type("IFCBEAM")
        if global_id(candidate) == beam.global_id
    )
    geometry = derive_beam_geometry(file, instance, source_ifc_sha256=digest)
    corroboration = corroborate_beam_section(
        session.world, file, beam, source_ifc_sha256=digest
    )
    return {
        "beam_geometry_issues": list(geometry.issues),
        "beam_geometry_status": str(geometry.status),
        "geometry_only_authority": str(
            authority_from_beam_status(str(geometry.status))
        ),
        "section_corroboration": corroboration.to_dict(),
        "section_modulus_source": "GAT_Structural declared property set",
    }


def _capacity_disposition(result, authority, support) -> dict[str, object]:
    """What each case policy makes of this capacity verdict.

    Both policies are recorded because the difference between them is the
    whole point of the support block. The as-built policy still wants field
    evidence for this exact world. The design-review policy does not -- but
    it does require sufficient support, so it can only reach ACCEPT once the
    declared section modulus is corroborated by the model's own solid.
    """
    case = AcceptanceCase(
        "beam-b1-capacity",
        WorkflowKind.OPENING_VERIFICATION,
        "Beam-B1 factored bending",
        (capacity_check("beam-b1-bending", result, authority, support=support),),
    )
    policies = {
        "as_built": evaluate_acceptance_case(case),
        "design_review": evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        ),
    }
    return {
        name: {
            "disposition": outcome.disposition.value,
            "insufficient_geometry_check_ids": list(
                outcome.insufficient_geometry_check_ids
            ),
            "may_authorize": outcome.may_authorize,
            "reasons": list(outcome.reasons),
        }
        for name, outcome in policies.items()
    }


def build_beam_records() -> dict[str, dict]:
    """The beam disposition, and the field packet that carries its certificate."""
    chain = _beam_chain()
    prior = chain["prior"]
    revised = chain["revised"]
    beam = chain["beam"]
    support = _beam_support(chain["session"], beam)
    authority = support["section_corroboration"]["authority"]

    disposition = {
        "beam": {
            "global_id": beam.global_id,
            "ifc_class": beam.ifc_class,
            "name": "Beam-B1",
        },
        "criterion": {
            "confidence": BEAM_CONFIDENCE,
            "factored_demand_n_m": BEAM_DEMAND_N_M,
        },
        "format": "gat-beam-disposition-v1",
        "model": "gat/demo/beam_model.ifc",
        "note": (
            "Replayable decision on the shipped beam IFC. A design-belief "
            "SATISFIED becomes VIOLATED once the measured material "
            "certificate is conditioned in. Digests identify the model's "
            "bytes, not this path. Read the support block before the "
            "verdicts: the model carries a W360X57 swept solid, so the "
            "declared plastic modulus Z is corroborated against an "
            "independently derived elastic modulus S through the shape "
            "factor. That earns DECLARED_CORROBORATED, which is why the "
            "design-review policy can reach ACCEPT on the prior belief. The "
            "as-built policy still returns REQUEST_EVIDENCE -- not for want "
            "of geometry now, but because a satisfied check still needs "
            "field evidence bound to this exact world. The certificate then "
            "makes the verdict VIOLATED, and REJECT wins regardless of "
            "support."
        ),
        "support": support,
        "prior": {
            "capacity_mean_n_m": prior.assessment.target_mean,
            "capacity_sigma_n_m": prior.assessment.target_sigma,
            "p_satisfies": prior.assessment.p_satisfies,
            "verdict": prior.verdict.value,
            "world_digest": chain["prior_world_digest"],
            "acceptance": _capacity_disposition(prior, authority, support),
        },
        "revised_after_certificate": {
            "capacity_mean_n_m": revised.assessment.target_mean,
            "capacity_sigma_n_m": revised.assessment.target_sigma,
            "p_satisfies": revised.assessment.p_satisfies,
            "verdict": revised.verdict.value,
            "world_digest": chain["result_world_digest"],
            "acceptance": _capacity_disposition(revised, authority, support),
        },
    }

    certificate_bytes = CERTIFICATE.read_bytes()
    # This repository's own fixture key, named explicitly: the packet proves
    # the certificate bytes are unaltered, not that an issuer vouched for them.
    trust_store = fixture_trust_store()
    signature = sign_certificate_bytes(
        certificate_bytes, key_id=TEST_KEY_ID, keys=trust_store
    )
    field_packet = {
        "calibration_id": "CAL-UTM-2026-08",
        "case_id": "beam-b1-certificate",
        "disposition": revised.verdict.value,
        "expected_prior_world_digest": chain["prior_world_digest"],
        "format": "gat-field-packet-v1",
        "note": (
            "Fixture packet with a real HMAC over the shipped certificate "
            "bytes under this repository's test key, whose secret is "
            "published in gat/engineering/certificate_signature.py. It proves "
            "the bytes were not altered between signing and use, and nothing "
            "more: not issuer accreditation, not a field lab, and not a key "
            "any real acceptance decision should trust."
        ),
        "quantity": "YieldStrengthMPa",
        "result_world_digest": chain["result_world_digest"],
        "signature": signature.to_dict(),
        "signature_verified": verify_certificate_bytes(
            certificate_bytes, signature, keys=trust_store
        ),
        "source_bytes_sha256": hashlib.sha256(certificate_bytes).hexdigest(),
        "source_path": "gat/demo/material_certificate.json",
        "subject_global_id": beam.global_id,
    }
    return {
        "beam-b1-disposition-v1.json": disposition,
        "field-packet-beam-b1-v1.json": field_packet,
    }


# -- scoped world on a real model -----------------------------------------


def build_clinic_record(corpus_root: str | os.PathLike[str]) -> dict:
    """One W460X60 lowered out of a real multi-storey structural model."""
    path = Path(corpus_root) / CLINIC_FILE
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    session = GatSession.load_ifc(
        str(path), scope=IfcLoweringScope(frozenset({CLINIC_BEAM}))
    )
    module = session.world.module
    entity = next(iter(module.entities))

    file = parse_ifc_file(str(path))
    beam = next(
        instance
        for instance in file.by_type("IFCBEAM")
        if global_id(instance) == CLINIC_BEAM
    )
    geometry = derive_beam_geometry(file, beam, source_ifc_sha256=source_sha)

    return {
        "beam_global_id": CLINIC_BEAM,
        "beam_name": geometry.beam_name,
        "derived_axis_length_m": geometry.axis_length.value,
        "derived_section_modulus_major_m3": geometry.section_modulus_major.value,
        "format": "gat-clinic-scoped-world-v1",
        "geometry_status": str(geometry.status),
        "has_yield_strength": "YieldStrengthMPa" in module.entities[entity].slots,
        "invariants_passed": session.verify().passed,
        "may_authorize_capacity": False,
        "module_digest": module.digest(),
        "note": (
            "Measured, not asserted. Scoped lowering of one W460X60 out of a "
            "real multi-storey IFC2X3 model. The body IS a complete swept "
            "solid, so the adapter can derive Zx from geometry -- but the beam "
            "carries no GAT_Structural property set, so no yield strength "
            "enters the world and no AISC capacity slot is synthesized. "
            "Capacity therefore cannot be checked from the model alone; it "
            "needs a material certificate. Digests identify the model's bytes, "
            "so this record reproduces wherever the corpus is fetched to."
        ),
        "raw_variables": session.world.binding.n_raw,
        "slots": sorted(module.entities[entity].slots),
        "source_ifc_sha256": source_sha,
        "source_name": CLINIC_FILE,
        "world_digest": session.world.digest(),
    }


# -- inventory -------------------------------------------------------------


def _inventory_case(case_id: str, path: Path, scope: IfcLoweringScope | None) -> dict:
    """What a model costs as *state*, and whether it lowers at all."""
    try:
        session = GatSession.load_ifc(str(path), scope=scope)
    except GatError as exc:
        return {
            "id": case_id,
            "lowers": False,
            "refusal": type(exc).__name__,
            "refusal_reason": str(exc)[:160],
        }
    raw = session.world.binding.n_raw
    # The clique counts are the fixture docs/sparse-belief-v1.md asks for: a
    # later factor-graph path must reproduce dense means on a world whose
    # structure is already written down here.
    factors = inventory_sparse_factors(session.world).to_dict()
    return {
        "id": case_id,
        "dense_covariance_entries": raw * raw,
        "derived_variables": session.world.binding.n_full - raw,
        "entities": len(session.world.module.entities),
        "ifc_factor_cliques": {
            "contains": factors["contains_cliques"],
            "fills": factors["fills_cliques"],
            "isolated_entities": factors["isolated_entities"],
            "voids": factors["voids_cliques"],
        },
        "lowers": True,
        "raw_variables": raw,
        "world_digest": session.world.digest(),
    }


_INVENTORY_NOTE = (
    "Reproducible state inventory: does a model lower, and how much belief "
    "does it become. No timings -- those are host-specific and live in "
    "incremental-scale-reference-v1.json, which names the machine it was "
    "measured on. This replaces benchmark-v1.json, which pinned wall-clock "
    "seconds next to world digests that were never measured."
)


def build_inventory_record() -> dict:
    """The models shipped in this repository. Always reproducible."""
    return {
        "cases": [
            _inventory_case("office-demo", OFFICE_MODEL, None),
            _inventory_case("beam-b1", BEAM_MODEL, None),
        ],
        "format": "gat-state-inventory-v1",
        "note": _INVENTORY_NOTE,
        "oracle": "dense-float64",
    }


def build_corpus_inventory_record(corpus_root: str | os.PathLike[str]) -> dict:
    """The commit-pinned public models. Needs the fetched corpus.

    Kept separate from the shipped-model inventory so each record reproduces
    in full under its own conditions, rather than one record silently losing
    rows on a host that has not fetched the corpus.
    """
    root = Path(corpus_root)
    return {
        "cases": [
            _inventory_case(
                "clinic-w460x60-scoped",
                root / CLINIC_FILE,
                IfcLoweringScope(frozenset({CLINIC_BEAM})),
            ),
            _inventory_case(
                "buildingsmart-wall-opening-window", root / WALL_OPENING_FILE, None
            ),
        ],
        "format": "gat-corpus-inventory-v1",
        "note": (
            "Public models from validation/ifc-corpus-v1.json. A refusal here "
            "is a result, not a failure: it records exactly why a real file "
            "cannot become state. " + _INVENTORY_NOTE
        ),
        "oracle": "dense-float64",
    }


# -- outcome log -----------------------------------------------------------


def build_outcome_log(records: dict[str, dict]) -> dict:
    """CSE's dispositions beside human decisions, where a human made one."""
    rows = [
        {
            "case_id": "opening-fit-demo",
            "subject": "Door-1 into Opening-1",
            "gat_disposition": records["opening-fit-disposition-v1.json"][
                "disposition"
            ],
            "human_decision": None,
            "matched": None,
            "source": "validation/opening-fit-disposition-v1.json",
        },
        {
            "case_id": "beam-b1-certificate",
            "subject": "Beam-B1 factored bending",
            "gat_disposition": records["beam-b1-disposition-v1.json"][
                "revised_after_certificate"
            ]["verdict"],
            "human_decision": None,
            "matched": None,
            "source": "validation/beam-b1-disposition-v1.json",
        },
    ]
    return {
        "format": "gat-outcome-log-v1",
        "note": (
            "Only cases where CSE actually returned a disposition through the "
            "evaluated pipeline. Human decisions are recorded only when a "
            "reviewer actually made one; empty cells are not implicit "
            "agreement. Every source names a record that exists in this "
            "repository and is regenerated by validation/regenerate.py. The "
            "clinic scoped world is deliberately absent: no capacity check can "
            "be formed on it at all, so it has no disposition to log -- see "
            "clinic-w460x60-scoped-world-v1.json for why."
        ),
        "rows": rows,
    }


# -- entry point -----------------------------------------------------------


def build_all(corpus_root: str | os.PathLike[str] | None = None) -> dict[str, dict]:
    """Every regenerable record, keyed by its filename in ``validation/``.

    ``corpus_root`` is the fetched public IFC corpus. Without it the
    corpus-dependent records are simply absent rather than stale.
    """
    records: dict[str, dict] = {}
    records.update(build_opening_fit_records())
    records.update(build_beam_records())
    records["state-inventory-v1.json"] = build_inventory_record()
    if corpus_root is not None:
        records["clinic-w460x60-scoped-world-v1.json"] = build_clinic_record(
            corpus_root
        )
        records["corpus-inventory-v1.json"] = build_corpus_inventory_record(
            corpus_root
        )
    records["outcome-log-v1.json"] = build_outcome_log(records)
    return records


def dumps(record: dict) -> str:
    """The exact on-disk form, so comparison is byte-for-byte."""
    return json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
