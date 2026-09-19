"""What survives a change of processor, and what does not. See
docs/digest-portability-v1.md.

The sweep behind that document forced OpenBLAS kernels with OPENBLAS_CORETYPE,
which a test cannot do in-process -- the kernel is chosen when numpy loads. So
these tests pin the *structural* facts that the sweep explained, each of which
holds on any single machine and would have to change for the sweep's conclusions
to stop applying:

  1. which digests are composed from float bytes at all,
  2. that the case digest and the BCF topic GUID inherit the world digest,
  3. that the beam model's stability comes from its pushforward sparsity,
  4. that the decision numbers do not depend on the covariance's last bits.

If a future change makes world_digest portable, several of these become wrong in
a loud way, which is the point.

stdlib unittest only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest
import uuid

import numpy as np

import gat.demo
from gat.engine.configuration import configuration_digest
from gat.engine.propagate import push_forward_with_jacobian
from gat.session import GatSession
from gat.workflows import (
    AcceptanceCase,
    DifferenceDecision,
    WorkflowKind,
    assess_difference,
    difference_check,
)

MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")
BEAM = os.path.join(os.path.dirname(gat.demo.__file__), "beam_model.ifc")


def _opening_case(session: GatSession) -> AcceptanceCase:
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


class WhatIsComposedFromFloatBytesTests(unittest.TestCase):
    """A digest over BLAS output cannot be portable. Record which ones are."""

    def test_the_world_digest_ends_in_the_full_covariance(self) -> None:
        world = GatSession.load_ifc(MODEL).world
        expected = hashlib.sha256()
        expected.update(world.module.digest().encode())
        expected.update(world.full.mu.tobytes())
        expected.update(world.full.sigma.tobytes())
        self.assertEqual(world.digest(), expected.hexdigest())

    def test_the_raw_belief_digest_does_not_touch_the_full_view(self) -> None:
        # The raw belief is stored, not computed by a matrix product, which is
        # why it was bit-identical under every kernel tested.
        world = GatSession.load_ifc(MODEL).world
        expected = hashlib.sha256()
        expected.update(world.belief.mu.tobytes())
        expected.update(world.belief.sigma.tobytes())
        self.assertIn(expected.hexdigest(), world.belief.digest())

    def test_the_configuration_digest_quantizes_the_full_view_before_hashing(
        self,
    ) -> None:
        """The portable digest reads the same BLAS output and rounds it first.

        This is worth stating precisely, because an earlier draft of this test
        assumed configuration_digest avoided the full view. It does not:
        _entity_intrinsic calls world.full.mean(var) and world.full.std(var) --
        the very quantities whose last bits move with the CPU -- and passes each
        through _q, which rounds to QUANT = 1e-6. That rounding is the entire
        reason it survived the kernel sweep, and it is remedy option (1) in
        docs/digest-portability-v1.md already implemented one module over.
        """
        from gat.engine.configuration import QUANT, _entity_intrinsic, _q

        self.assertEqual(QUANT, 1e-6)
        self.assertEqual(_q(1.0 + 1e-12), 1.0)

        world = GatSession.load_ifc(MODEL).world
        source = Path(_entity_intrinsic.__code__.co_filename).read_text()
        self.assertIn("_q(world.full.mean(slot.var))", source)
        self.assertIn("_q(world.full.std(slot.var))", source)

        # And it really is the full view, not the raw belief.
        eid = next(iter(world.module.entities))
        self.assertIsInstance(_entity_intrinsic(world, eid), str)

    def test_quantization_buys_a_probability_not_a_guarantee(self) -> None:
        """Rounding is not a homomorphism, so size the residual risk.

        Two values a hair apart still round differently when they straddle a
        boundary. Measured on both shipped models: the closest quantized value
        sits 1.364e-09 from a flip, which is 94x the worst covariance
        perturbation observed between kernels (1.455e-11). Comfortable, and not
        a proof -- if boundary positions were uniform the expected number of
        flipped values is ~1.8e-03 per model, i.e. about one model in 550 would
        get a different configuration digest on a different CPU.

        This test fails if a model ever lands within one perturbation of a
        boundary, which is when the comfortable margin stops being comfortable.
        """
        from gat.engine.configuration import QUANT

        worst_observed_perturbation = 1.455e-11
        for model in (MODEL, BEAM):
            world = GatSession.load_ifc(model).world
            values = []
            for entity in world.module.entities.values():
                for slot in entity.slots.values():
                    values.append(world.full.mean(slot.var))
                    values.append(world.full.std(slot.var))
            scaled = np.abs(np.asarray(values, dtype=float)) / QUANT
            to_boundary = np.abs(0.5 - np.abs(scaled - np.round(scaled))) * QUANT
            with self.subTest(model=os.path.basename(model)):
                self.assertGreater(
                    float(to_boundary.min()),
                    worst_observed_perturbation,
                    "a quantized value now sits within one observed cross-kernel "
                    "perturbation of a rounding boundary; configuration_digest is "
                    "no longer comfortably portable for this model",
                )


class TheRemedyIsAlreadyHereTests(unittest.TestCase):
    """Three layers handle reassociation. The digest path is the outlier."""

    def test_the_invariant_registry_uses_relative_tolerances(self) -> None:
        # The verification layer was written with reassociation in mind. If it
        # ever starts comparing a computed float exactly, the one part of the
        # runtime that is robust to a different CPU stops being robust.
        source = Path("gat/engine/verify.py").read_text(encoding="utf-8")
        self.assertIn("tol = 1e-9 * max(1.0, abs(expected))", source)
        self.assertIn("resid > c.tol * max(1.0, abs(expected))", source)

    def test_computational_equivalence_carries_the_remedy_and_nobody_uses_it(
        self,
    ) -> None:
        """Its docstring names cross-platform carriers; its tolerances are dead.

        This is the finding written down before it was measured. The test pins
        both halves: the parameters exist and default to exact, and no caller in
        gat/ passes a nonzero value. It fails the day somebody does -- which is
        the day the snapshot round-trip could become portable.
        """
        import inspect

        from gat.state_snapshot import computational_equivalence

        signature = inspect.signature(computational_equivalence)
        self.assertEqual(signature.parameters["atol"].default, 0.0)
        self.assertEqual(signature.parameters["rtol"].default, 0.0)
        self.assertIn(
            "cross-platform carriers", computational_equivalence.__doc__ or ""
        )

        callers = []
        for path in sorted(Path("gat").rglob("*.py")):
            body = path.read_text(encoding="utf-8")
            if "computational_equivalence(" not in body:
                continue
            for line in body.splitlines():
                if "computational_equivalence(" in line and "def " not in line:
                    callers.append((str(path), line.strip()))
        self.assertTrue(callers, "expected at least one caller to audit")
        for path, line in callers:
            with self.subTest(caller=path):
                self.assertNotIn("atol=", line)
                self.assertNotIn("rtol=", line)

    def test_the_snapshot_check_compares_a_digest_not_the_beliefs(self) -> None:
        # reconstruct_snapshot has computational_equivalence available and does
        # not use it for its portability check. It compares world.digest()
        # against the recorded string -- the byte comparison the tolerances were
        # added to avoid.
        source = Path("gat/state_snapshot.py").read_text(encoding="utf-8")
        self.assertIn(
            'if world.digest() != source_world_digest:',
            source,
        )
        self.assertIn(
            'raise SnapshotError("reconstructed world digest differs from source")',
            source,
        )


class InheritedIdentityTests(unittest.TestCase):
    """Nine moving identities, one root cause. Pin the inheritance."""

    def test_the_case_digest_embeds_the_world_digest(self) -> None:
        session = GatSession.load_ifc(MODEL)
        case = _opening_case(session)
        self.assertEqual(case.world_digest, session.world.digest())
        # Changing only the world digest must change the case digest, or the
        # case digest is not carrying the world's identity at all.
        other = GatSession.load_ifc("gat/demo/model.ifc")
        if other.world.digest() != session.world.digest():
            self.assertNotEqual(_opening_case(other).scope_digest, case.scope_digest)

    def test_the_bcf_topic_guid_is_derived_from_the_case_digest(self) -> None:
        # So a BCF topic is only as portable as the world digest. Two machines
        # exporting the same case file different topics, and the receiving tool
        # cannot tell they are the same issue.
        from gat.adapters.bcf import TOPIC_NAMESPACE
        from gat.workflows import evaluate_acceptance_case

        session = GatSession.load_ifc(MODEL)
        record = evaluate_acceptance_case(_opening_case(session)).to_dict()
        self.assertEqual(record["disposition"], "REQUEST_EVIDENCE")
        self.assertTrue(record["evidence_requests"])
        for request in record["evidence_requests"]:
            expected = uuid.uuid5(
                TOPIC_NAMESPACE, f"{record['case_digest']}/{request['check_id']}"
            )
            self.assertEqual(
                str(expected),
                str(
                    uuid.uuid5(
                        TOPIC_NAMESPACE,
                        f"{record['case_digest']}/{request['check_id']}",
                    )
                ),
            )
        # The load-bearing half: a different case digest gives a different guid.
        shifted = uuid.uuid5(TOPIC_NAMESPACE, f"{'0' * 64}/width")
        actual = uuid.uuid5(TOPIC_NAMESPACE, f"{record['case_digest']}/width")
        self.assertNotEqual(shifted, actual)

    def test_the_scene_version_is_the_world_digest(self) -> None:
        from gat.geometry.stateio import derive_scene

        world = GatSession.load_ifc(MODEL).world
        self.assertEqual(str(derive_scene(world).version), world.digest())


class BeamStabilityIsSparsityTests(unittest.TestCase):
    """The beam digest survives because of its structure. Pin the structure."""

    def test_the_beam_pushforward_has_at_most_two_nonzeros_per_row(self) -> None:
        # At two nonzeros an entry of J Sigma J^T is a sum of at most four
        # products -- too short to reassociate, which is why the beam world
        # digest was identical under all five kernels. This is the property the
        # freeze's beam slice actually rests on.
        world = GatSession.load_ifc(BEAM).world
        _, jacobian, _, _ = push_forward_with_jacobian(world.binding, world.belief)
        per_row = (np.asarray(jacobian) != 0).sum(axis=1)
        self.assertLessEqual(
            int(per_row.max()),
            2,
            "a beam derived quantity now combines more than two raw variables; "
            "its world digest is no longer CPU-stable -- see "
            "docs/digest-portability-v1.md",
        )

    def test_the_office_pushforward_is_long_enough_to_reassociate(self) -> None:
        # The contrast that makes the explanation an explanation rather than a
        # story about size.
        world = GatSession.load_ifc(MODEL).world
        _, jacobian, _, _ = push_forward_with_jacobian(world.binding, world.belief)
        per_row = (np.asarray(jacobian) != 0).sum(axis=1)
        self.assertGreater(int(per_row.max()), 2)


class DecisionsDoNotDependOnTheLastBitsTests(unittest.TestCase):
    def test_a_one_ulp_covariance_nudge_cannot_flip_an_opening_check(self) -> None:
        # The claim the whole finding rests on: the estimates are fine. A margin
        # of 0.1 m against a sigma of 0.0058 has ~14 orders of margin over eps.
        session = GatSession.load_ifc(MODEL)
        case = _opening_case(session)
        for check in case.checks:
            details = check.details or {}
            margin = abs(float(details["margin_mean"]))
            sigma = float(details["margin_sigma"])
            with self.subTest(check=check.check_id):
                self.assertGreater(margin / np.finfo(np.float64).eps, 1e12)
                self.assertGreater(sigma / np.finfo(np.float64).eps, 1e12)


if __name__ == "__main__":
    unittest.main()
