"""One definition of a bind, and the things that are not one.

`docs/cse-point-bind-v1.md` lists four rules. Until this file, three of them were
enforced only by a duck-type in the inspectability fold -- schema, a non-empty
point_id, a non-empty global_id -- while `gat.harness.point_bind.bind_point`
required frame, epoch and sigma as well. Two definitions of "a bind" in one tree,
with the fold using the weak one, is how every MCP client ends up inventing its
own shape and all of them being accepted.

`validation/cse-point-bind-v1.schema.json` writes the strict definition down, the
fold delegates to the validator, and these tests pin the rules the doc states:

    gat.harness --commit files never satisfy bind.point_to_guid
    a JSON object that only says schema: cse-point-bind-v1 is not a bind
    a paragraph from an MCP agent is not a bind
    binding Opening-1 does not change Beam-B1 or shrink Sigma

stdlib unittest only.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import gat.demo
from gat.harness.inspectability import _is_bind, bind_refusals, fold_inspectability
from gat.harness.point_bind import (
    FORBIDDEN_KEYS,
    _looks_like_display_name,
    assert_bind_in_world,
    bind_point,
    bind_point_file,
)
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = _ROOT / "validation" / "cse-point-bind-v1.schema.json"
EXAMPLE = _ROOT / "validation" / "cse-point-bind-v1.json"
FIXTURES = Path(gat.demo.__file__).resolve().parent / "harness_fixtures"
STRICT_FIXTURE = FIXTURES / "p204-opening-bind.json"
SPACE = FIXTURES / "space-l3-office-a.json"
OPENING_1 = "GATOPN0000000000000200"


def _fold(*binds) -> dict:
    space = json.loads(SPACE.read_text(encoding="utf-8"))
    index = fold_inspectability(
        space=space,
        receipts=[],
        commitments=[],
        binds=[(document, source) for document, source in binds],
    )
    return index.document


def _bind_hole(document: dict) -> dict | None:
    for row in document["open_requests"]:
        if row["code"] == "bind.point_to_guid":
            return row
    return None


class SchemaFileTests(unittest.TestCase):
    """The schema exists as a file, so a client can check before it writes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    def test_the_schema_requires_what_the_validator_requires(self) -> None:
        # If these drift, a client can satisfy the file and still be refused by
        # the code, which is worse than having no schema at all.
        self.assertEqual(self.schema["$id"], "cse-point-bind-v1")
        self.assertEqual(
            set(self.schema["required"]),
            {"schema", "claim_scope", "point_id", "global_id", "ifc_class", "payload"},
        )
        self.assertEqual(
            set(self.schema["properties"]["payload"]["required"]),
            {
                "point_id",
                "global_id",
                "ifc_class",
                "frame_id",
                "epoch",
                "sigma",
                "sigma_unit",
                "sigma_reason",
            },
        )
        self.assertEqual(
            self.schema["properties"]["claim_scope"]["const"], "record-integrity-only"
        )

    def test_the_schema_lists_the_bindable_classes_the_code_allows(self) -> None:
        from gat.harness.point_bind import ALLOWED_IFC_CLASSES

        self.assertEqual(
            set(self.schema["properties"]["ifc_class"]["enum"]), set(ALLOWED_IFC_CLASSES)
        )

    def test_the_schema_carries_the_three_evidence_fields_as_optional(self) -> None:
        # quantity says which slot a bind licenses; receipt_digest links it to a
        # receipt; world_digest says which lowering the Guid was checked against.
        # Optional, because bind.point_to_guid is an identity hole and
        # evidence.as_built is a different one -- a bind that cites a receipt is
        # still only an identity claim.
        payload = self.schema["properties"]["payload"]
        for field in ("quantity", "receipt_digest", "world_digest"):
            with self.subTest(field=field):
                self.assertIn(field, payload["properties"])
                self.assertNotIn(field, payload["required"])

    def test_the_schema_says_what_a_bind_is_not(self) -> None:
        claims = self.schema["not_claimed"]
        self.assertIn("a bind is not field evidence", claims)
        self.assertIn("a gat.harness --commit digest is not a bind", claims)
        self.assertIn(
            "a JSON object that only says schema: cse-point-bind-v1 is not a bind",
            claims,
        )
        self.assertIn("a paragraph from an MCP agent is not a bind", claims)


class TheShippedExampleIsOneTests(unittest.TestCase):
    def test_the_canonical_example_validates(self) -> None:
        """The repository's own example of the schema must be an instance of it.

        It was not. It declared claim_scope identity-bind-only and carried no
        sigma, frame or epoch, so the validator that defines cse-point-bind-v1
        refused the file named cse-point-bind-v1.json -- while the fold's
        duck-type accepted it. That is the drift this test exists to stop.
        """
        bind = bind_point_file(EXAMPLE)
        self.assertEqual(bind.point_id, "P-Opening-1")
        self.assertEqual(bind.global_id, OPENING_1)
        self.assertEqual(bind.sigma, 0.005)
        self.assertEqual(bind.sigma_unit, "m")
        self.assertTrue(bind.sigma_reason)

    def test_the_example_does_not_invent_a_digest_it_cannot_have(self) -> None:
        # world_digest is machine-local; receipt_digest would point at nothing.
        # Both are absent and the file says why, which is better than a plausible
        # 64-hex string that is true nowhere.
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        payload = document["payload"]
        self.assertNotIn("world_digest", payload)
        self.assertNotIn("receipt_digest", payload)
        self.assertIn("world_digest", document["omitted_on_purpose"])
        self.assertIn("receipt_digest", document["omitted_on_purpose"])

    def test_the_strict_fixture_the_demos_use_also_validates(self) -> None:
        bind = bind_point_file(STRICT_FIXTURE)
        self.assertEqual(bind.point_id, "P-204")


class OneDefinitionTests(unittest.TestCase):
    """The fold and the validator must not disagree about any document."""

    def test_the_fold_delegates_to_the_validator(self) -> None:
        candidates = [
            json.loads(EXAMPLE.read_text(encoding="utf-8")),
            json.loads(STRICT_FIXTURE.read_text(encoding="utf-8")),
            {"schema": "cse-point-bind-v1"},
            {"schema": "cse-point-bind-v1", "point_id": "P", "global_id": OPENING_1},
            {"schema": "something-else"},
            {},
        ]
        for document in candidates:
            with self.subTest(schema=document.get("schema")):
                try:
                    bind_point(document)
                    strict = True
                except ValueError:
                    strict = False
                self.assertIs(_is_bind(document), strict)

    def test_a_malformed_bind_leaves_the_hole_open_rather_than_aborting(self) -> None:
        # The fold reports what is missing. A bad bind must not raise through it
        # and hide identity.space or evidence.as_built.
        document = _fold(({"schema": "cse-point-bind-v1"}, "junk.json"))
        codes = {row["code"] for row in document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)
        self.assertIn("evidence.as_built", codes)


class WhatIsNotABindTests(unittest.TestCase):
    """The four rules from docs/cse-point-bind-v1.md, as failures."""

    def test_a_harness_commit_file_is_not_a_bind(self) -> None:
        """gat.harness --commit files never satisfy bind.point_to_guid.

        A commit binds an external measurement digest. It carries a sigma and a
        reason, which is most of what a bind needs, and that is exactly why it has
        to be refused by name rather than by accident: it says nothing about which
        IfcGuid the point is.
        """
        commit = json.loads(
            (FIXTURES / "p204-opening-measurement-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(commit["schema"], "cse-measurement-v1")
        self.assertIn("sigma", commit)  # it has a sigma
        self.assertNotIn("global_id", commit)  # and no Guid

        with self.assertRaises(ValueError):
            bind_point(commit)
        self.assertFalse(_is_bind(commit))

        document = _fold((commit, "p204-opening-measurement-v1.json"))
        hole = _bind_hole(document)
        self.assertIsNotNone(hole)
        self.assertIn("p204-opening-measurement-v1.json", hole["refused"])

    def test_a_commit_relabelled_as_a_bind_is_still_not_one(self) -> None:
        # The obvious next move for a client that wants the hole closed: keep the
        # measurement and change the schema string.
        commit = json.loads(
            (FIXTURES / "p204-opening-measurement-v1.json").read_text(encoding="utf-8")
        )
        relabelled = {**commit, "schema": "cse-point-bind-v1"}
        self.assertFalse(_is_bind(relabelled))
        with self.assertRaisesRegex(ValueError, "point_id"):
            bind_point(relabelled)

    def test_schema_only_is_not_a_bind(self) -> None:
        self.assertFalse(_is_bind({"schema": "cse-point-bind-v1"}))

    def test_an_mcp_agent_paragraph_is_not_a_bind(self) -> None:
        """A paragraph from an MCP agent is not a bind.

        The realistic failure: an agent that has read the docs writes the fields
        it can see named, in prose, with no frame, epoch or sigma. Four fields
        used to be enough.
        """
        invented = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-204",
            "global_id": OPENING_1,
            "ifc_class": "IfcOpeningElement",
            "note": "P-204 is the setting-out point for Opening-1 per the layout plan.",
        }
        self.assertFalse(_is_bind(invented))
        refused = bind_refusals([(invented, "mcp-agent.json")])
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]["source"], "mcp-agent.json")
        self.assertTrue(refused[0]["refused"])

        hole = _bind_hole(_fold((invented, "mcp-agent.json")))
        self.assertIsNotNone(hole)
        self.assertIn("mcp-agent.json", hole["refused"])

    def test_a_display_name_is_not_a_global_id(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["global_id"] = "Opening-1"
        document["payload"]["global_id"] = "Opening-1"
        document.pop("digest", None)
        with self.assertRaisesRegex(ValueError, "not a display name"):
            bind_point(document)

    def test_coordinates_without_a_guid_are_not_a_bind(self) -> None:
        with self.assertRaisesRegex(ValueError, "coordinates without an IfcGuid"):
            bind_point(
                {
                    "schema": "cse-point-bind-v1",
                    "claim_scope": "record-integrity-only",
                    "xyz": [1.0, 2.0, 3.0],
                }
            )

    def test_a_bind_without_sigma_is_refused(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        del document["payload"]["sigma"]
        document.pop("digest", None)
        with self.assertRaisesRegex(ValueError, "sigma"):
            bind_point(document)

    def test_a_declared_digest_that_does_not_match_is_refused(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            bind_point(document)


class TheOpenBagTests(unittest.TestCase):
    """The required set is strict. The bag is open. Pin what that costs.

    A bind file legitimately carries prose -- a note, an omitted_on_purpose block,
    a surveyor's name -- so closing the schema would reject the next honest field.
    Open also means an agent can write ``authorized: true``. The cost is bounded
    three ways: those keys are refused by name, unknown keys are outside the
    digest, and PointBind.to_document() drops them.
    """

    @staticmethod
    def _with(where: str, key: str, value: object) -> dict:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document.pop("digest", None)
        target = document if where == "root" else document["payload"]
        target[key] = value
        return document

    def test_an_authority_claim_is_refused_by_name_not_dropped(self) -> None:
        """Silently dropping it is safe for the runtime and wrong for the author.

        Someone who wrote ``authorized: true`` into a bind and saw it accepted
        would believe the bind carried an authority it never had. FORBIDDEN_KEYS
        is not an open-ended blocklist; it is this repository's authority
        vocabulary.
        """
        for where in ("root", "payload"):
            for key in sorted(FORBIDDEN_KEYS):
                with self.subTest(where=where, key=key):
                    with self.assertRaises(ValueError) as caught:
                        bind_point(self._with(where, key, True))
                    self.assertIn("cannot claim", str(caught.exception))

    def test_a_second_claim_scope_is_refused(self) -> None:
        # One record, one scope. A nested one reads like a narrower promise than
        # the root makes.
        with self.assertRaisesRegex(ValueError, "second claim_scope"):
            bind_point(self._with("payload", "claim_scope", "field-evidence"))

    def test_harmless_extra_keys_are_still_allowed(self) -> None:
        document = self._with("root", "note", "crew note")
        document["payload"]["surveyor"] = "R. Okafor"
        bind = bind_point(document)
        self.assertEqual(bind.point_id, "P-Opening-1")

    def test_extra_keys_change_no_scope_and_close_no_other_hole(self) -> None:
        """The test the open bag requires: extra keys buy nothing.

        The bind hole closes because the bind is valid. identity.space and
        evidence.as_built stay exactly as they were -- a bind cannot buy a scan by
        carrying a word.
        """
        space = json.loads(SPACE.read_text(encoding="utf-8"))
        plain = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        loaded = self._with("root", "note", "crew note")
        loaded["payload"]["surveyor"] = "R. Okafor"
        loaded["payload"]["confidence"] = "high"

        for label, document in (("plain", plain), ("loaded", loaded)):
            with self.subTest(bind=label):
                index = fold_inspectability(
                    space=space, receipts=[], commitments=[], binds=[(document, "b.json")]
                )
                codes = {row["code"] for row in index.document["open_requests"]}
                self.assertNotIn("bind.point_to_guid", codes)
                self.assertIn("evidence.as_built", codes)
                self.assertEqual(
                    bind_point(document).to_document()["claim_scope"],
                    "record-integrity-only",
                )

    def test_unknown_keys_are_outside_the_digest(self) -> None:
        plain = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        plain.pop("digest", None)
        loaded = self._with("payload", "surveyor", "R. Okafor")
        self.assertEqual(bind_point(plain).digest, bind_point(loaded).digest)

    def test_unknown_keys_do_not_survive_to_document(self) -> None:
        # So an agent-supplied word cannot reach a packet a human reads.
        document = self._with("payload", "surveyor", "R. Okafor")
        emitted = bind_point(document).to_document()
        self.assertNotIn("surveyor", emitted["payload"])
        self.assertNotIn("surveyor", emitted)


class TheGuidCheckIsNotTheRegexTests(unittest.TestCase):
    """_looks_like_display_name is lint. assert_bind_in_world is the identity law."""

    def test_the_lint_catches_this_projects_display_names_and_little_else(self) -> None:
        for flagged in ("Opening-1", "Beam-B1", "Door-3", "Room A"):
            with self.subTest(value=flagged):
                self.assertTrue(_looks_like_display_name(flagged))
        # And these sail through, which is the point of calling it lint.
        for missed in ("RoomA", "GATOPN00000000000002", "1xS3BCk291UvhgP2a6eTKA"):
            with self.subTest(value=missed):
                self.assertFalse(_looks_like_display_name(missed))

    def test_a_name_the_lint_misses_is_stopped_by_the_world(self) -> None:
        """The executable version of "the regex is not the Guid law".

        RoomA is not a GlobalId, the lint does not flag it, bind_point accepts it,
        and assert_bind_in_world refuses it. If anyone reads the pattern as the
        identity check, this is the case that shows the gap.
        """
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document.pop("digest", None)
        document["global_id"] = document["payload"]["global_id"] = "RoomA"

        bind = bind_point(document)  # lint does not stop it
        self.assertEqual(bind.global_id, "RoomA")

        world = GatSession.load_ifc(
            str(Path(gat.demo.__file__).resolve().parent / "model.ifc")
        ).world
        with self.assertRaisesRegex(ValueError, "not in the compiled world"):
            assert_bind_in_world(bind, world)

    def test_a_truncated_guid_is_also_only_stopped_by_the_world(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document.pop("digest", None)
        truncated = OPENING_1[:-2]
        document["global_id"] = document["payload"]["global_id"] = truncated
        self.assertFalse(_looks_like_display_name(truncated))
        world = GatSession.load_ifc(
            str(Path(gat.demo.__file__).resolve().parent / "model.ifc")
        ).world
        with self.assertRaises(ValueError):
            assert_bind_in_world(bind_point(document), world)


class QuantitySurvivesValidationTests(unittest.TestCase):
    """quantity is in the schema and read by the budget seam, so it must round trip."""

    def test_quantity_survives_a_validate_and_reserialise(self) -> None:
        """It did not. PointBind dropped it and to_document rebuilt payload.

        So a bind that had been validated and written back out lost its quantity,
        and gat.adapters.budget_cite then refused the very bind bind_point had
        just accepted. Found by running the seam on a round-tripped bind.
        """
        bind = bind_point_file(EXAMPLE)
        self.assertEqual(bind.quantity, "Width")
        emitted = bind_point(bind.to_document())
        self.assertEqual(emitted.quantity, "Width")
        self.assertEqual(emitted.digest, bind.digest)

    def test_quantity_is_part_of_the_identity(self) -> None:
        # A bind licensing Width is a different claim from one licensing Height.
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document.pop("digest", None)
        width = bind_point(document).digest
        document["payload"]["quantity"] = "Height"
        self.assertNotEqual(bind_point(document).digest, width)

    def test_a_short_digest_prefix_is_not_a_digest(self) -> None:
        # One width for every digest in a bind. A reader should never have to
        # guess whether a 16-character string is whole or the front of one.
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document.pop("digest", None)
        document["payload"]["receipt_digest"] = "a" * 16
        with self.assertRaisesRegex(ValueError, "prefix is not a digest"):
            bind_point(document)
        document["payload"]["receipt_digest"] = "a" * 64
        self.assertEqual(bind_point(document).receipt_digest, "a" * 64)

    def test_the_shipped_p204_fixture_round_trips(self) -> None:
        bind = bind_point_file(STRICT_FIXTURE)
        self.assertEqual(bind.quantity, "Width")
        self.assertEqual(bind.point_id, "P-204")
        # Its declared digest matches, which is what makes the file self-checking.
        declared = json.loads(STRICT_FIXTURE.read_text(encoding="utf-8"))["digest"]
        self.assertEqual(bind.digest, declared)


class ABindMovesNothingTests(unittest.TestCase):
    """Binding Opening-1 does not change Beam-B1 or shrink Sigma.

    The kernel-adjacency guard. A bind is a record; if reading one could move a
    digest or a belief it would be a transform wearing a filename.
    """

    def test_reading_a_bind_moves_no_digest_and_no_belief(self) -> None:
        model = str(Path(gat.demo.__file__).resolve().parent / "model.ifc")
        session = GatSession.load_ifc(model)
        before_world = session.world.digest()
        before_config = session.world.belief.digest()
        before_sigma = session.world.belief.sigma.tobytes()

        bind = bind_point_file(EXAMPLE)
        self.assertEqual(bind.global_id, OPENING_1)

        from gat.harness.point_bind import assert_bind_in_world

        assert_bind_in_world(bind, session.world)

        self.assertEqual(session.world.digest(), before_world)
        self.assertEqual(session.world.belief.digest(), before_config)
        self.assertEqual(session.world.belief.sigma.tobytes(), before_sigma)

    def test_a_bind_for_an_absent_guid_fails_closed(self) -> None:
        from gat.harness.point_bind import assert_bind_in_world

        model = str(Path(gat.demo.__file__).resolve().parent / "beam_model.ifc")
        beam_session = GatSession.load_ifc(model)
        bind = bind_point_file(EXAMPLE)  # names an opening, not a beam
        with self.assertRaisesRegex(ValueError, "not in the compiled world"):
            assert_bind_in_world(bind, beam_session.world)


if __name__ == "__main__":
    unittest.main()
