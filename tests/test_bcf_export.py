"""A disposition leaves the runtime in a format someone else can open.

BCF 2.1 is how the construction industry exchanges "this needs attention", so
exporting a disposition gives it the second consumer this runtime has never had
-- and it works on the pinned dispositions in validation/, which until now were
read by nothing at all.

Two properties are asserted here because a generic BCF writer would lose them:
the export is deterministic (GUIDs derived from the case digest, fixed zip
timestamps, no clock read), and it carries the claim scope, so a topic cannot be
mistaken for an approval once it is out of the runtime.

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
    NOT_AN_APPROVAL,
    BcfExportError,
    bcf_topics,
    read_topic_guids,
    topic_guid,
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
        identity = {"portable_digest": "f" * 64, "source": "gat/demo/model.ifc"}
        topics = bcf_topics(
            self.pin, created=CREATED, author=AUTHOR, world_identity=identity
        )
        self.assertIn("f" * 64, topics[0]["description"])


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
