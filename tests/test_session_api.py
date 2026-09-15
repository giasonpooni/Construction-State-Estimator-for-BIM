"""The GatSession public surface is a contract, not an accident.

`main` once carried a `GatSession` that had lost 19 of its 20 public methods
to a bad merge.  Every downstream module still imported it, so the failure
surfaced as 221 unrelated test errors rather than as one clear message.
This module pins the surface itself: if a constructor, a recorder, or an
exporter disappears again, exactly one test fails and it says which.
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

import gat.session as session_module
from gat.engine.transform import SetParameter
from gat.errors import GatError
from gat.ids import VarId
from gat.session import GatSession


#: Every public entry point the engine, CLI, demos, and headless boundary
#: rely on.  Adding to this set is fine; removing from it is a breaking
#: change that must be deliberate.
REQUIRED_SURFACE: frozenset[str] = frozenset(
    {
        # constructors
        "load_ifc",
        "from_text",
        "load_snapshot",
        "load_openusd",
        "load_usd",
        # queries
        "entity_by_name",
        "var",
        "verify",
        # execution
        "run",
        # causal record keeping
        "record_assessment",
        "record_policy",
        "record_approval",
        "record_external_action",
        # exports
        "export_ifc",
        "export_json",
        "export_usd",
        "export_openusd",
        "export_snapshot",
        "export_ledger",
    }
)

#: Constructors are classmethods; losing that binding breaks every caller.
REQUIRED_CLASSMETHODS: frozenset[str] = frozenset(
    {"load_ifc", "from_text", "load_snapshot", "load_openusd", "load_usd"}
)


class SessionSurfaceTests(unittest.TestCase):
    def test_every_required_method_is_present_and_callable(self) -> None:
        missing = sorted(
            name
            for name in REQUIRED_SURFACE
            if not callable(getattr(GatSession, name, None))
        )
        self.assertEqual(
            missing,
            [],
            "GatSession lost public methods: " + ", ".join(missing),
        )

    def test_constructors_are_classmethods(self) -> None:
        for name in sorted(REQUIRED_CLASSMETHODS):
            with self.subTest(constructor=name):
                attribute = inspect.getattr_static(GatSession, name)
                self.assertIsInstance(
                    attribute,
                    classmethod,
                    f"GatSession.{name} must stay a classmethod",
                )

    def test_instances_expose_the_audit_state(self) -> None:
        for name in ("world", "trace", "ledger", "initial_report"):
            with self.subTest(attribute=name):
                self.assertIn(
                    name,
                    inspect.getsource(GatSession.__init__),
                    f"GatSession.__init__ must still establish {name!r}",
                )

    def test_load_ifc_accepts_a_lowering_scope(self) -> None:
        signature = inspect.signature(GatSession.load_ifc)
        self.assertIn("scope", signature.parameters)
        self.assertIsNone(signature.parameters["scope"].default)


class RejectionRecordTests(unittest.TestCase):
    """Every attempt reaches the ledger, including the ones that crash.

    ``run`` caught ``GatError`` and nothing else. A declared refusal was
    recorded; an undeclared failure inside ``execute`` propagated with no
    event written at all. The state was never at risk -- ``self.world`` is
    only assigned on success -- but the ledger is what says what was
    attempted against this world, and it was silently short one event.
    """

    def _session(self):
        return GatSession.load_ifc("gat/demo/model.ifc")

    def test_an_undeclared_failure_is_still_recorded(self) -> None:
        session = self._session()
        transformation = SetParameter(
            session.var("Wall-South", "Length"), 5.0, 0.01
        )
        before = len(session.ledger.events)
        digest = session.world.digest()

        with patch.object(
            session_module, "execute", side_effect=ValueError("engine fault")
        ):
            with self.assertRaises(ValueError) as caught:
                session.run(transformation)

        # Re-raised as itself: a runtime fault must not be dressed up as a
        # decision the operation earned.
        self.assertEqual(str(caught.exception), "engine fault")
        self.assertNotIsInstance(caught.exception, GatError)

        self.assertEqual(len(session.ledger.events), before + 1)
        event = session.ledger.events[-1]
        self.assertEqual(event.kind, "rejection")
        self.assertEqual(event.error_type, "ValueError")
        self.assertEqual(session.world.digest(), digest)

    def test_a_failure_to_record_does_not_replace_the_failure(self) -> None:
        """If the ledger itself cannot take the event, the caller must still
        see what actually went wrong."""
        session = self._session()
        transformation = SetParameter(
            session.var("Wall-South", "Length"), 5.0, 0.01
        )
        with patch.object(
            session_module, "execute", side_effect=ValueError("engine fault")
        ):
            with patch.object(
                session.ledger, "record_rejection",
                side_effect=RuntimeError("ledger is unavailable"),
            ):
                with self.assertRaises(ValueError) as caught:
                    session.run(transformation)
        self.assertEqual(str(caught.exception), "engine fault")

    def test_a_commit_and_a_declared_refusal_are_recorded_as_before(self) -> None:
        """The widened boundary must not change what already worked."""
        session = self._session()
        before = len(session.ledger.events)

        session.run(SetParameter(session.var("Wall-South", "Length"), 5.0, 0.01))
        self.assertEqual(len(session.ledger.events), before + 1)
        self.assertEqual(session.ledger.events[-1].kind, "transition")

        ghost = VarId(session.entity_by_name("Wall-South"), "NotAQuantity")
        with self.assertRaises(GatError):
            session.run(SetParameter(ghost, 1.0, 0.01))
        self.assertEqual(len(session.ledger.events), before + 2)
        event = session.ledger.events[-1]
        self.assertEqual(event.kind, "rejection")
        self.assertEqual(event.error_type, "BindingError")


if __name__ == "__main__":
    unittest.main()
