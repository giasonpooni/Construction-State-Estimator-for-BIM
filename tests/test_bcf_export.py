"""A disposition leaves the runtime in a format someone else can open.

BCF 2.1 is how the construction industry exchanges "this needs attention", so
exporting a disposition gives it the second consumer this runtime has never had
-- and it works on the pinned dispositions in validation/, which until now were
read by nothing at all.

Three properties are asserted here because a generic BCF writer would lose them:
the export is deterministic (derived GUIDs, fixed zip timestamps, no clock read),
it carries the claim scope so a topic cannot be mistaken for an approval once it
is out of the runtime, and a topic GUID is portable across processors whenever an
identity record is supplied -- or says it is not, when one is absent.

The portability class below reproduces the real defect rather than mocking it: the
same case on another CPU is the same model, the same belief to twelve significant
digits, and a DIFFERENT world_digest and case_digest. That is what a second
engineer's export looks like, and the machine-local GUID moves under it while the
portable one does not.

stdlib unittest only.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from gat.adapters.bcf import (
    BCF_VERSION,
    IDENTITY_MACHINE_LOCAL,
    IDENTITY_PORTABLE,
    IDENTITY_SCHEMA,
    NOT_AN_APPROVAL,
    BcfExportError,
    bcf_topics,
    portable_topic_key,
    read_topic_guids,
    topic_guid,
    topic_identity,
    write_bcfzip,
)

_ROOT = Path(__file__).resolve().parents[1]
PIN = _ROOT / "validation" / "opening-fit-disposition-v1.json"
DESIGN_REVIEW = _ROOT / "validation" / "opening-fit-design-review-disposition-v1.json"
CREATED = "2026-09-18T12:00:00Z"
AUTHOR = "cse@notation.systems"

# BCF 2.1 declares Topic's children as an ordered sequence; a validating reader
# rejects any other order.
TOPIC_SEQUENCE = ["Title", "Priority", "Labels", "CreationDate", "CreationAuthor", "Description"]

#: A portable digest is not derivable from a pinned document -- the document is
#: all there is -- so it arrives from outside, which is exactly how the real
#: caller supplies it.
PORTABLE = "1f" * 32


def identity_for(document, **overrides) -> dict:
    """The record ``portable_identity.world_identity()`` emits, for this pin.

    Built by hand rather than from a live world on purpose: the world whose
    digest the pin carries is machine-local, so computing it here would make this
    test fail on the processors it exists to defend.
    """
    record = {
        "schema": IDENTITY_SCHEMA,
        "claim_scope": "record-integrity-only",
        "world_digest": document["world_digest"],
        "portable_digest": PORTABLE,
        "portable_significant_digits": 12,
        "source": "gat/demo/model.ifc",
    }
    record.update(overrides)
    return record


class BcfTopicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads(PIN.read_text(encoding="utf-8"))
        cls.topics = bcf_topics(cls.pin, created=CREATED, author=AUTHOR)

    def test_one_topic_per_evidence_request(self) -> None:
        self.assertEqual(len(self.topics), len(self.pin["evidence_requests"]))
        self.assertEqual([t["status"] for t in self.topics], ["Open", "Open"])

    def test_topics_come_out_in_check_id_order(self) -> None:
        self.assertEqual(
            [t["title"].split(":")[0] for t in self.topics],
            ["Door-1 height fit", "Door-1 width fit"],
        )

    def test_guids_are_derived_not_generated(self) -> None:
        again = bcf_topics(self.pin, created=CREATED, author=AUTHOR)
        self.assertEqual([t["guid"] for t in again], [t["guid"] for t in self.topics])
        self.assertEqual(
            self.topics[0]["guid"], topic_guid(self.pin["case_digest"], "height")
        )

    def test_a_different_case_digest_gives_different_guids(self) -> None:
        self.assertNotEqual(topic_guid("a" * 64, "width"), topic_guid("b" * 64, "width"))

    def test_every_topic_says_it_is_not_an_approval(self) -> None:
        for topic in self.topics:
            self.assertIn(NOT_AN_APPROVAL, topic["description"])
            self.assertIn("may_authorize: False", topic["description"])
            self.assertIn("claim_scope:record-integrity-only", topic["labels"])

    def test_every_topic_cites_the_world_it_was_computed_on(self) -> None:
        for topic in self.topics:
            self.assertIn(self.pin["world_digest"], topic["description"])
            self.assertIn(self.pin["case_digest"], topic["description"])

    def test_the_check_detail_travels_with_the_request(self) -> None:
        # A reviewer needs the margin, not just "evidence required".
        height = self.topics[0]["description"]
        self.assertIn("margin_mean", height)
        self.assertIn("minimum_margin", height)
        self.assertIn("geometry_authority", height)

    def test_a_clock_is_never_read(self) -> None:
        with self.assertRaisesRegex(BcfExportError, "creation date"):
            bcf_topics(self.pin, created="", author=AUTHOR)
        with self.assertRaisesRegex(BcfExportError, "creation date"):
            bcf_topics(self.pin, created=CREATED, author="")

    def test_the_portable_digest_is_carried_when_offered(self) -> None:
        topics = bcf_topics(
            self.pin,
            created=CREATED,
            author=AUTHOR,
            world_identity=identity_for(self.pin),
        )
        self.assertIn(PORTABLE, topics[0]["description"])

    def test_a_bare_dict_cannot_relabel_topics_portable(self) -> None:
        """The old shape of this test, now refused.

        ``{"portable_digest": ...}`` with no schema and no world_digest used to be
        accepted and its digest printed in the body. It names no world, so nothing
        establishes that the number belongs to this disposition.
        """
        with self.assertRaisesRegex(BcfExportError, "must be cse-world-identity-v1"):
            bcf_topics(
                self.pin,
                created=CREATED,
                author=AUTHOR,
                world_identity={"portable_digest": "f" * 64},
            )


class BcfArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads(PIN.read_text(encoding="utf-8"))

    def test_archive_layout_is_bcf_21(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bcfzip"
            guids = write_bcfzip(path, self.pin, created=CREATED, author=AUTHOR)
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                self.assertIn("bcf.version", names)
                for guid in guids:
                    self.assertIn(f"{guid}/markup.bcf", names)
                version = ET.fromstring(archive.read("bcf.version"))
                self.assertEqual(version.get("VersionId"), BCF_VERSION)

    def test_topic_children_follow_the_schema_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bcfzip"
            guids = write_bcfzip(path, self.pin, created=CREATED, author=AUTHOR)
            with zipfile.ZipFile(path) as archive:
                markup = ET.fromstring(archive.read(f"{guids[0]}/markup.bcf"))
            topic = markup.find("Topic")
            order = [child.tag for child in topic]
            deduped = [tag for i, tag in enumerate(order) if i == 0 or order[i - 1] != tag]
            self.assertEqual(deduped, TOPIC_SEQUENCE)
            self.assertEqual(topic.get("TopicType"), "Issue")
            self.assertIsNotNone(markup.find("Comment"))

    def test_two_exports_are_byte_identical(self) -> None:
        # The whole point: a BCF file can be digested and replayed.
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.bcfzip", Path(tmp) / "b.bcfzip"
            write_bcfzip(first, self.pin, created=CREATED, author=AUTHOR)
            write_bcfzip(second, self.pin, created=CREATED, author=AUTHOR)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_guids_round_trip_out_of_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bcfzip"
            guids = write_bcfzip(path, self.pin, created=CREATED, author=AUTHOR)
            self.assertEqual(list(read_topic_guids(path)), sorted(guids))

    def test_an_accept_with_nothing_to_do_refuses_to_pretend(self) -> None:
        # The design-review pin ACCEPTs and raises no request. Emitting an empty
        # BCF file would tell a reviewer there is work when there is none.
        accept = json.loads(DESIGN_REVIEW.read_text(encoding="utf-8"))
        self.assertEqual(accept["disposition"], "ACCEPT")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BcfExportError, "nothing for a reviewer"):
                write_bcfzip(
                    Path(tmp) / "out.bcfzip", accept, created=CREATED, author=AUTHOR
                )

    def test_a_document_without_a_case_digest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BcfExportError, "case_digest"):
                write_bcfzip(
                    Path(tmp) / "out.bcfzip",
                    {"disposition": "REQUEST_EVIDENCE", "evidence_requests": []},
                    created=CREATED,
                    author=AUTHOR,
                )


class BcfCliTests(unittest.TestCase):
    """gat bcf is the usable surface; the CLI may read a clock, the library may not."""

    def test_cli_writes_an_archive_and_reports_zero(self) -> None:
        from gat.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.bcfzip"
            code = main(
                ["bcf", str(PIN), "-o", str(out), "--created", CREATED, "--author", AUTHOR]
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.is_file())
            self.assertEqual(len(read_topic_guids(out)), 2)

    def test_cli_defaults_the_timestamp_rather_than_failing(self) -> None:
        from gat.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.bcfzip"
            self.assertEqual(main(["bcf", str(PIN), "-o", str(out)]), 0)
            self.assertTrue(out.is_file())

    def test_cli_returns_two_when_there_is_nothing_to_act_on(self) -> None:
        from gat.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.bcfzip"
            self.assertEqual(main(["bcf", str(DESIGN_REVIEW), "-o", str(out)]), 2)
            self.assertFalse(out.exists())

    def test_cli_world_identity_produces_the_portable_guids(self) -> None:
        from gat.cli import main

        document = json.loads(PIN.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "identity.json"
            record.write_text(json.dumps(identity_for(document)), encoding="utf-8")
            portable, local = Path(tmp) / "p.bcfzip", Path(tmp) / "l.bcfzip"
            self.assertEqual(
                main(["bcf", str(PIN), "-o", str(portable),
                      "--created", CREATED, "--world-identity", str(record)]),
                0,
            )
            self.assertEqual(
                main(["bcf", str(PIN), "-o", str(local), "--created", CREATED]), 0
            )
            expected = [
                str(topic["guid"])
                for topic in bcf_topics(
                    document,
                    created=CREATED,
                    author=AUTHOR,
                    world_identity=identity_for(document),
                )
            ]
            self.assertEqual(sorted(read_topic_guids(portable)), sorted(expected))
            self.assertNotEqual(
                sorted(read_topic_guids(portable)), sorted(read_topic_guids(local))
            )

    def test_cli_refuses_an_identity_for_another_world_rather_than_ignoring_it(self) -> None:
        """Exit 2, not a quiet fall back to machine-local GUIDs.

        Supplying the wrong identity file is a mistake worth stopping for: the
        export would otherwise succeed and be labelled portable on a number from
        a different run.
        """
        from gat.cli import main

        document = json.loads(PIN.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "stranger.json"
            record.write_text(
                json.dumps(identity_for(document, world_digest="99" * 32)),
                encoding="utf-8",
            )
            out = Path(tmp) / "out.bcfzip"
            self.assertEqual(
                main(["bcf", str(PIN), "-o", str(out),
                      "--created", CREATED, "--world-identity", str(record)]),
                2,
            )
            self.assertFalse(out.exists())


class BcfLiveDispositionTests(unittest.TestCase):
    """The same export runs on a freshly computed outcome, not only on a pin."""

    def test_a_live_outcome_exports_and_carries_both_identities(self) -> None:
        import zipfile as _zip

        from gat.adapters.portable_identity import world_identity
        from gat.session import GatSession
        from gat.workflows import (
            AcceptanceCase,
            DifferenceDecision,
            WorkflowKind,
            assess_difference,
            difference_check,
            evaluate_acceptance_case,
        )

        session = GatSession.load_ifc(str(_ROOT / "gat" / "demo" / "model.ifc"))
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
        case = AcceptanceCase(
            "opening-fit-live",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            tuple(checks),
        )
        document = evaluate_acceptance_case(case).to_dict()
        identity = world_identity(session.world)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "live.bcfzip"
            guids = write_bcfzip(
                out,
                document,
                created=CREATED,
                author=AUTHOR,
                world_identity=identity,
            )
            self.assertEqual(len(guids), 2)
            with _zip.ZipFile(out) as archive:
                body = archive.read(f"{guids[0]}/markup.bcf").decode("utf-8")
        self.assertIn(identity["portable_digest"], body)
        self.assertIn(document["world_digest"], body)
        # A live case digest differs from the pinned one, so the GUIDs do too.
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        self.assertNotEqual(document["case_digest"], pin["case_digest"])
        self.assertNotIn(topic_guid(pin["case_digest"], "height"), guids)


if __name__ == "__main__":
    unittest.main()


class TopicIdentityTests(unittest.TestCase):
    """Which identity a topic GUID rests on, and what moves it.

    The defect: ``case_digest`` embeds ``world_digest``, and ``World.digest()``
    hashes ``full.sigma.tobytes()``, which BLAS sums in a CPU-dependent order. So
    two engineers exporting the same case on different hardware got different
    topics -- the one defect of that kind visible without opening hex.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads(PIN.read_text(encoding="utf-8"))

    def _guids(self, document, identity=None) -> list[str]:
        return [
            str(topic["guid"])
            for topic in bcf_topics(
                document, created=CREATED, author=AUTHOR, world_identity=identity
            )
        ]

    def _on_another_processor(self) -> dict:
        """The same case, exported by a second engineer.

        Same model, same belief to twelve significant digits -- so the same
        portable digest -- and a different local digest, because sigma's bytes
        differ in the last bits. Nothing else about the case changes.
        """
        other = json.loads(json.dumps(self.pin))
        other["world_digest"] = "ab" * 32
        other["case_digest"] = "cd" * 32
        for check in other["checks"]:
            check["world_digest"] = "ab" * 32
        return other

    # -- the fix ------------------------------------------------------------
    def test_the_portable_guid_survives_a_change_of_processor(self) -> None:
        here = self._guids(self.pin, identity_for(self.pin))
        there = self._guids(
            self._on_another_processor(), identity_for(self._on_another_processor())
        )
        self.assertEqual(here, there)

    def test_the_machine_local_guid_does_not(self) -> None:
        """The defect itself, asserted so the fix has something to be a fix of."""
        self.assertNotEqual(
            self._guids(self.pin), self._guids(self._on_another_processor())
        )

    def test_the_two_kinds_of_guid_are_different_guids(self) -> None:
        self.assertNotEqual(
            self._guids(self.pin), self._guids(self.pin, identity_for(self.pin))
        )

    # -- the old behaviour is still exactly the old behaviour ----------------
    def test_without_an_identity_record_nothing_moved(self) -> None:
        key, kind = topic_identity(self.pin, None)
        self.assertEqual(key, self.pin["case_digest"])
        self.assertEqual(kind, IDENTITY_MACHINE_LOCAL)
        self.assertEqual(
            self._guids(self.pin),
            [topic_guid(self.pin["case_digest"], c) for c in ("height", "width")],
        )

    # -- which identity, said out loud --------------------------------------
    def test_every_topic_says_which_identity_its_guid_rests_on(self) -> None:
        for identity, kind in ((None, IDENTITY_MACHINE_LOCAL),
                               (identity_for(self.pin), IDENTITY_PORTABLE)):
            with self.subTest(kind=kind):
                topics = bcf_topics(
                    self.pin, created=CREATED, author=AUTHOR, world_identity=identity
                )
                for topic in topics:
                    self.assertEqual(topic["identity"], kind)
                    self.assertIn(f"identity:{kind}", topic["labels"])
                    self.assertIn(f"topic GUID identity: {kind}", topic["description"])

    def test_a_machine_local_export_warns_in_the_body_a_reviewer_reads(self) -> None:
        body = str(self._describe_first(None))
        self.assertIn("specific to the processor", body)
        self.assertIn("may be a DIFFERENT topic", body)

    def test_a_portable_export_states_the_thirteenth_digit_aliasing(self) -> None:
        body = str(self._describe_first(identity_for(self.pin)))
        self.assertIn("13th significant digit", body)
        self.assertIn("keeps its GUID across re-exports", body)

    def _describe_first(self, identity):
        return bcf_topics(
            self.pin, created=CREATED, author=AUTHOR, world_identity=identity
        )[0]["description"]

    # -- what the portable key is a function of ----------------------------
    def test_a_verdict_does_not_move_the_portable_guid(self) -> None:
        """Stated in the docstring, so asserted rather than left to be found.

        A verdict is a float comparison, so near a threshold it is precisely what
        does not survive a change of processor. Keeping it out is the point; the
        consequence is that a topic keeps its GUID while its status moves, which
        is what tracking a topic in a reviewer's tool needs.
        """
        flipped = json.loads(json.dumps(self.pin))
        for check in flipped["checks"]:
            check["verdict"] = "VIOLATED"
            check["confidence"] = 0.12
            check["p_satisfies_lower"] = 0.01
        self.assertEqual(
            portable_topic_key(self.pin, PORTABLE),
            portable_topic_key(flipped, PORTABLE),
        )

    def test_a_different_question_does_move_it(self) -> None:
        for field, value in (
            ("case_id", "another-case"),
            ("subject", "Door-2 into Opening-1"),
            ("policy_id", "gat-design-review-v1"),
            ("workflow", "ACCEPTANCE"),
        ):
            with self.subTest(field=field):
                other = dict(self.pin, **{field: value})
                self.assertNotEqual(
                    portable_topic_key(self.pin, PORTABLE),
                    portable_topic_key(other, PORTABLE),
                )

    def test_a_check_changing_kind_moves_it(self) -> None:
        other = json.loads(json.dumps(self.pin))
        other["checks"][0]["kind"] = "CLEARANCE"
        self.assertNotEqual(
            portable_topic_key(self.pin, PORTABLE),
            portable_topic_key(other, PORTABLE),
        )

    def test_a_different_belief_moves_it(self) -> None:
        self.assertNotEqual(
            portable_topic_key(self.pin, PORTABLE),
            portable_topic_key(self.pin, "2e" * 32),
        )

    def test_the_key_does_not_depend_on_check_order(self) -> None:
        shuffled = json.loads(json.dumps(self.pin))
        shuffled["checks"].reverse()
        self.assertEqual(
            portable_topic_key(self.pin, PORTABLE),
            portable_topic_key(shuffled, PORTABLE),
        )

    # -- refusals -----------------------------------------------------------
    def test_an_identity_for_another_world_is_refused(self) -> None:
        stranger = identity_for(self.pin, world_digest="99" * 32)
        with self.assertRaisesRegex(BcfExportError, "different world"):
            topic_identity(self.pin, stranger)

    def test_an_identity_with_no_portable_digest_is_refused(self) -> None:
        record = identity_for(self.pin)
        del record["portable_digest"]
        with self.assertRaisesRegex(BcfExportError, "no portable_digest"):
            topic_identity(self.pin, record)

    def test_a_prefix_is_not_a_portable_digest(self) -> None:
        for bad in (PORTABLE[:16], PORTABLE.upper(), "", "zz" * 32):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(BcfExportError, "64-character"):
                    topic_identity(self.pin, identity_for(self.pin, portable_digest=bad))

    def test_a_non_mapping_identity_is_refused(self) -> None:
        with self.assertRaisesRegex(BcfExportError, "JSON object or None"):
            topic_identity(self.pin, ["not", "a", "record"])

    def test_a_document_with_no_case_digest_and_no_identity_is_refused(self) -> None:
        naked = {k: v for k, v in self.pin.items() if k != "case_digest"}
        with self.assertRaisesRegex(BcfExportError, "case_digest"):
            topic_identity(naked, None)

    # -- replay still holds, on both paths ---------------------------------
    def test_a_portable_export_is_still_byte_identical_twice(self) -> None:
        identity = identity_for(self.pin)
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.bcfzip", Path(tmp) / "b.bcfzip"
            for path in (first, second):
                write_bcfzip(
                    path,
                    self.pin,
                    created=CREATED,
                    author=AUTHOR,
                    world_identity=identity,
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_the_archive_is_named_by_the_portable_guid(self) -> None:
        identity = identity_for(self.pin)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bcfzip"
            guids = write_bcfzip(
                path,
                self.pin,
                created=CREATED,
                author=AUTHOR,
                world_identity=identity,
            )
            self.assertEqual(sorted(read_topic_guids(path)), sorted(guids))
            self.assertNotEqual(
                sorted(guids),
                sorted(self._guids(self.pin)),
            )
