"""The shared design language: one palette, fail-closed human rendering."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import gat.demo
from gat import report
from gat.cli import main as cli_main
from gat.headless import REQUEST_FORMAT, handle_request


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "integrations" / "blender" / "gat_assurance" / "bridge.py"
MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")
BEAM_MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "beam_model.ifc")
MATERIAL_CERTIFICATE = os.path.join(
    os.path.dirname(gat.demo.__file__),
    "material_certificate.json",
)

spec = importlib.util.spec_from_file_location("gat_report_bridge", BRIDGE)
assert spec is not None and spec.loader is not None
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


def request(operation: str, payload: dict, model: str = MODEL) -> dict:
    return {
        "format": REQUEST_FORMAT,
        "request_id": f"report-{operation}",
        "operation": operation,
        "state": {"kind": "ifc", "path": model},
        "payload": payload,
    }


def acceptance_response() -> dict:
    return handle_request(
        request(
            "acceptance",
            {
                "case_id": "opening-fit-1",
                "workflow": "OPENING_VERIFICATION",
                "subject": "Door-1 into Opening-1",
                "checks": [
                    {
                        "kind": "difference",
                        "check_id": "width",
                        "lhs": {"entity_name": "Opening-1", "quantity": "Width"},
                        "rhs": {"entity_name": "Door-1", "quantity": "Width"},
                        "minimum_margin": 0.05,
                        "confidence": 0.95,
                        "label": "opening width fit",
                    }
                ],
            },
        )
    )


def acceptance_response_at(confidence: float, minimum_margin: float) -> dict:
    """The same opening-fit case at a caller-chosen bar and margin."""
    payload = {
        "case_id": "opening-fit-1",
        "workflow": "OPENING_VERIFICATION",
        "subject": "Door-1 into Opening-1",
        "checks": [
            {
                "kind": "difference",
                "check_id": "width",
                "lhs": {"entity_name": "Opening-1", "quantity": "Width"},
                "rhs": {"entity_name": "Door-1", "quantity": "Width"},
                "minimum_margin": minimum_margin,
                "confidence": confidence,
                "label": "opening width fit",
            }
        ],
    }
    return handle_request(request("acceptance", payload))


def beam_response() -> dict:
    return handle_request(
        request(
            "beam_assurance",
            {
                "case_id": "beam-b1-certificate",
                "beam_name": "Beam-B1",
                "factored_demand_n_m": 301_000.0,
                "confidence": 0.95,
                "material_certificate_path": MATERIAL_CERTIFICATE,
                "label": "Beam-B1 factored bending",
            },
            model=BEAM_MODEL,
        )
    )


def change_response() -> dict:
    return handle_request(
        request(
            "change_impact",
            {
                "change": {
                    "op": "set_parameter",
                    "target": {"entity_name": "Wall-Party", "quantity": "Length"},
                    "value": 5.2,
                    "design_sigma": 0.01,
                }
            },
        )
    )


class PaletteLockstepTests(unittest.TestCase):
    def test_shared_terms_match_the_blender_panel_bit_for_bit(self) -> None:
        for term in (
            "ACCEPT",
            "REJECT",
            "REQUEST_EVIDENCE",
            "SATISFIED",
            "VIOLATED",
            "UNRESOLVED",
        ):
            self.assertEqual(
                report.disposition_color(term),
                bridge.disposition_color(term),
                term,
            )

    def test_unknown_vocabulary_is_refused_not_guessed(self) -> None:
        with self.assertRaises(ValueError):
            report.disposition_color("MAYBE")
        with self.assertRaises(ValueError):
            report.disposition_hex("MAYBE")

    def test_hex_values_match_the_documented_palette(self) -> None:
        self.assertEqual(report.disposition_hex("ACCEPT"), "#1ab233")
        self.assertEqual(report.disposition_hex("VIOLATED"), "#d91414")
        self.assertEqual(report.disposition_hex("UNRESOLVED"), "#f28c0d")
        self.assertEqual(report.disposition_hex("ERROR"), "#595959")


class SummaryRenderingTests(unittest.TestCase):
    def test_summary_renders_state_and_footers(self) -> None:
        decoded = report.decode_response(handle_request(request("summary", {})))
        self.assertEqual(decoded.disposition, "PASS")
        text = report.render_text(decoded)
        self.assertIn("PASS: ", text)
        self.assertIn("12 pass / 0 warn / 0 fail", text)
        self.assertIn("24 raw + 39 derived variables", text)
        self.assertIn(report.NON_AUTHORIZING_FOOTER, text)
        self.assertIn(report.READ_ONLY_FOOTER, text)

    def test_summary_refuses_verified_claim_with_failures(self) -> None:
        response = handle_request(request("summary", {}))
        tampered = copy.deepcopy(response)
        tampered["result"]["verification"]["failure_count"] = 1
        with self.assertRaises(ValueError):
            report.decode_response(tampered)


class AcceptanceRenderingTests(unittest.TestCase):
    def test_request_evidence_case_shows_checks_and_next_evidence(self) -> None:
        decoded = report.decode_response(acceptance_response())
        self.assertEqual(decoded.disposition, "REQUEST_EVIDENCE")
        self.assertEqual(decoded.headline, "REQUEST_EVIDENCE: Door-1 into Opening-1")
        text = report.render_text(decoded)
        self.assertIn("OPENING_VERIFICATION case opening-fit-1", text)
        self.assertIn("SATISFIED", text)
        self.assertIn("next evidence", text)
        self.assertIn("gat-safe-acceptance-v1", text)
        self.assertIn(report.NON_AUTHORIZING_FOOTER, text)

    def test_inconsistent_authorization_claim_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["may_authorize"] = True
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_unknown_disposition_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["disposition"] = "PROBABLY_FINE"
        with self.assertRaises(ValueError):
            report.decode_response(tampered)


class AcceptanceDispositionFollowsItsVerdictsTests(unittest.TestCase):
    """The disposition must follow from the verdicts rendered beside it.

    Before the fix ``_acceptance_report`` validated the disposition
    vocabulary, the world digest, ``may_authorize`` and each verdict's
    vocabulary, and then never compared the two. Measured on the tampered
    demo response: disposition "ACCEPT" over one VIOLATED check decoded
    without refusing and rendered headline 'ACCEPT: Door-1 into Opening-1',
    banner #1ab233 (proceed green) and the footer 'Recommendation only;
    professional approval is still required.' -- the one footer that invites
    action -- above a checks row reading 'width DIFFERENCE VIOLATED'. With
    "checks": [] the same green ACCEPT rendered over a checks table with a
    header and zero rows, no contradiction visible at all. "REJECT" over a
    lone SATISFIED check and "REQUEST_EVIDENCE" over a VIOLATED check also
    rendered. ``python -m gat report forged.json`` printed each and exited 0.
    None is engine-representable: workflows/acceptance.py takes REJECT on any
    VIOLATED check before every other branch, and AcceptanceCase.__post_init__
    refuses a case with no checks.
    """

    def test_accept_over_a_violated_check_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["disposition"] = "ACCEPT"
        tampered["result"]["may_authorize"] = True
        tampered["result"]["checks"][0]["verdict"] = "VIOLATED"
        with self.assertRaises(ValueError) as caught:
            report.decode_response(tampered)
        message = str(caught.exception)
        self.assertIn("ACCEPT", message)
        self.assertIn("width", message)
        self.assertIn("VIOLATED", message)

    def test_accept_over_an_unresolved_check_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["disposition"] = "ACCEPT"
        tampered["result"]["may_authorize"] = True
        tampered["result"]["checks"][0]["verdict"] = "UNRESOLVED"
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_disposition_over_zero_checks_is_refused(self) -> None:
        for disposition, may_authorize in (
            ("ACCEPT", True),
            ("REQUEST_EVIDENCE", False),
        ):
            tampered = copy.deepcopy(acceptance_response())
            tampered["result"]["disposition"] = disposition
            tampered["result"]["may_authorize"] = may_authorize
            tampered["result"]["checks"] = []
            with self.assertRaises(ValueError) as caught:
                report.decode_response(tampered)
            self.assertIn("no checks", str(caught.exception))

    def test_reject_with_no_violated_check_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["disposition"] = "REJECT"
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_request_evidence_over_a_violated_check_is_refused(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["checks"][0]["verdict"] = "VIOLATED"
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_engine_dispositions_still_render(self) -> None:
        # The guard must not cost the cases the engine does emit: an
        # unresolved case (REQUEST_EVIDENCE over UNRESOLVED) and a satisfied
        # one still awaiting evidence (REQUEST_EVIDENCE over SATISFIED).
        for margin in (0.05, 0.0855):
            decoded = report.decode_response(
                acceptance_response_at(0.95, margin)
            )
            self.assertEqual(decoded.disposition, "REQUEST_EVIDENCE")
            self.assertIn(report.NON_AUTHORIZING_FOOTER, report.render_text(decoded))

    def test_cli_refuses_a_forged_accept_and_exits_two(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["disposition"] = "ACCEPT"
        tampered["result"]["may_authorize"] = True
        tampered["result"]["checks"][0]["verdict"] = "VIOLATED"
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "forged.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(tampered, handle)
            self.assertNotEqual(cli_main(["report", path]), 0)


class ConfidenceColumnIsTheDecisionBarTests(unittest.TestCase):
    """The confidence cell is the bar the verdict was decided against.

    gat/report.py:436 rendered it as ``f"{confidence:.0%}"``. Measured on
    untampered engine responses for this demo model: confidence 0.994 with
    minimum_margin 0.0855 gives p_satisfies_lower 0.9935538305 and verdict
    UNRESOLVED, and the row rendered 'width DIFFERENCE UNRESOLVED 0.99355
    99%' -- a five-decimal probability that reads as clearing the whole-
    percent bar it actually failed. The whole top of the band collapsed:
    0.995, 0.999 and 0.9999 all rendered '100%', a bar AcceptanceCheck
    guarantees no confidence can be (0.5 < confidence < 1.0). The documented
    rule is five decimals (docs/design-language-v1.md "Value formatting").
    """

    def test_a_confidence_below_the_bar_is_not_rounded_up_to_it(self) -> None:
        response = acceptance_response_at(0.994, 0.0855)
        check = response["result"]["checks"][0]
        self.assertEqual(check["verdict"], "UNRESOLVED")
        self.assertLess(check["p_satisfies_lower"], check["confidence"])
        text = report.render_text(report.decode_response(response))
        row = next(
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("width  DIFFERENCE")
        )
        self.assertIn("0.99400", row)
        self.assertNotIn("99%", row)

    def test_the_strictly_below_one_band_never_renders_as_certainty(self) -> None:
        for confidence in (0.995, 0.999, 0.9999):
            text = report.render_text(
                report.decode_response(acceptance_response_at(confidence, 0.05))
            )
            self.assertNotIn("100%", text)
            self.assertIn(report.format_probability(confidence), text)

    def test_html_carries_the_same_cell_as_the_terminal(self) -> None:
        decoded = report.decode_response(acceptance_response_at(0.994, 0.0855))
        html = report.render_html(decoded)
        self.assertIn("<td>0.99400</td>", html)
        self.assertNotIn("<td>99%</td>", html)


class BeamRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.response = beam_response()

    def test_verdict_change_capacity_and_honest_assurance_flags(self) -> None:
        decoded = report.decode_response(self.response)
        self.assertEqual(decoded.disposition, "VIOLATED")
        text = report.render_text(decoded)
        self.assertIn("VIOLATED: Beam-B1", text)
        self.assertIn("prior SATISFIED -> revised VIOLATED", text)
        self.assertIn("315.0 +- 7.9 kN*m -> 293.8 +- 3.4 kN*m", text)
        self.assertIn("0.96258 -> 0.01788", text)
        self.assertIn("ansi-aisc-360-22-f2-1-lrfd-v1", text)
        self.assertIn("issuer_trust_verified                    no", text)
        self.assertIn(report.NON_AUTHORIZING_FOOTER, text)

    def test_unverified_beam_response_is_refused(self) -> None:
        tampered = copy.deepcopy(self.response)
        tampered["result"]["verification"]["passed"] = False
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_authorizing_beam_response_is_refused(self) -> None:
        tampered = copy.deepcopy(self.response)
        tampered["result"]["assurance"]["may_authorize"] = True
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_world_identity_mismatch_is_refused(self) -> None:
        tampered = copy.deepcopy(self.response)
        tampered["result"]["prior"]["world_digest"] = "0" * 64
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_verdict_change_claim_must_be_consistent(self) -> None:
        tampered = copy.deepcopy(self.response)
        tampered["result"]["decision_change"]["verdict_changed"] = False
        with self.assertRaises(ValueError):
            report.decode_response(tampered)


class ChangeRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.response = change_response()

    def test_preview_renders_impacts_and_preview_footer(self) -> None:
        decoded = report.decode_response(self.response)
        self.assertEqual(decoded.disposition, "ADMISSIBLE")
        self.assertEqual(decoded.subject, "set_parameter IfcWall.Length = 5.2")
        text = report.render_text(decoded)
        self.assertIn("design-change preview", text)
        self.assertIn("target", text)
        self.assertIn("affected", text)
        self.assertIn(report.PREVIEW_FOOTER, text)
        self.assertIn(report.READ_ONLY_FOOTER, text)

    def test_admissibility_claim_must_match_failures(self) -> None:
        tampered = copy.deepcopy(self.response)
        tampered["result"]["disposition"] = "BLOCKED"
        tampered["result"]["admissible"] = False
        with self.assertRaises(ValueError):
            report.decode_response(tampered)


class HtmlRenderingTests(unittest.TestCase):
    def test_html_is_self_contained_and_script_free(self) -> None:
        decoded = report.decode_response(beam_response())
        html = report.render_html(decoded)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn(report.disposition_hex("VIOLATED"), html)
        self.assertIn("<details", html)
        self.assertIn(decoded.world_digest, html)

    def test_html_honours_system_theme_and_prints_full_digests(self) -> None:
        decoded = report.decode_response(beam_response())
        html = report.render_html(decoded)
        self.assertIn('<meta name="color-scheme" content="light dark">', html)
        self.assertIn("@media (prefers-color-scheme: dark)", html)
        self.assertIn("@media print", html)
        self.assertIn(f'<span class="print-digest">{decoded.world_digest}</span>', html)
        # signal colours are semantic: the dark block redefines tokens only
        dark_block = html.split("@media (prefers-color-scheme: dark)", 1)[1].split("} }", 1)[0]
        for signal_hex in ("#1ab233", "#d91414", "#f28c0d", "#595959"):
            self.assertNotIn(signal_hex, dark_block)

    def test_fragment_is_the_body_of_the_page(self) -> None:
        decoded = report.decode_response(beam_response())
        fragment = report.render_html_fragment(decoded)
        page = report.render_html(decoded)
        self.assertIn(fragment, page)
        self.assertTrue(fragment.startswith('<header class="banner"'))
        self.assertTrue(fragment.endswith("</footer>"))
        self.assertNotIn("<html", fragment)
        self.assertNotIn("<style", fragment)

    def test_html_escapes_untrusted_response_text(self) -> None:
        tampered = copy.deepcopy(acceptance_response())
        tampered["result"]["reasons"] = ["<img src=x onerror=alert(1)>"]
        html = report.render_html(report.decode_response(tampered))
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)


class ErrorRenderingTests(unittest.TestCase):
    def test_error_response_renders_grey_and_undecided(self) -> None:
        decoded = report.decode_response(
            {
                "format": report.RESPONSE_FORMAT,
                "error": {"type": "ValueError", "message": "boom"},
            }
        )
        self.assertEqual(decoded.disposition, "ERROR")
        self.assertEqual(decoded.operation, "error")
        text = report.render_text(decoded)
        self.assertIn("ERROR: ValueError", text)
        self.assertIn("boom", text)
        self.assertIn(report.READ_ONLY_FOOTER, text)


class LedgerTimelineTests(unittest.TestCase):
    def build_ledger(self, tmp: str) -> str:
        from gat.causal import AssessmentRecord
        from gat.engine.transform import ShiftParameter
        from gat.session import GatSession

        session = GatSession.load_ifc(MODEL)
        session.run(
            ShiftParameter(session.var("Wall-Party", "Length"), 0.1),
            provenance={"phase": "test-shift"},
        )
        session.record_assessment(
            AssessmentRecord(
                world_digest=session.world.digest(),
                assessment_id="fit-1",
                assessment_type="test-assessment",
                subject="Wall-Party",
                verdict="VIOLATED",
                method="test-method-v1",
            ),
            provenance={"phase": "test-assessment"},
        )
        path = os.path.join(tmp, "ledger.json")
        session.export_ledger(path)
        return path

    def test_timeline_renders_chain_events_and_accents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            decoded = report.decode_ledger(self.build_ledger(tmp))
            self.assertEqual(decoded.operation, "ledger")
            self.assertEqual(decoded.disposition, "PASS")
            text = report.render_text(decoded)
            self.assertIn("0 - genesis", text)
            self.assertIn("1 - transition: shift_parameter", text)
            self.assertIn("2 - assessment", text)
            self.assertIn("hash chain verified", text)
            self.assertIn(report.READ_ONLY_FOOTER, text)
            html = report.render_html(decoded)
            self.assertNotIn("<script", html)
            self.assertIn('class="stop"', html)
            self.assertIn("VIOLATED", html)

    def test_tampered_chain_is_refused_not_drawn(self) -> None:
        from gat.errors import LedgerError

        with tempfile.TemporaryDirectory() as tmp:
            path = self.build_ledger(tmp)
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
            document["events"][1]["operation"]["delta"] = 0.5
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
            with self.assertRaises(LedgerError):
                report.decode_ledger(path)
            self.assertEqual(cli_main(["ledger", path]), 2)

    def test_cli_renders_timeline_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build_ledger(tmp)
            self.assertEqual(cli_main(["ledger", path, "-o", os.devnull]), 0)
            out = os.path.join(tmp, "timeline.html")
            self.assertEqual(cli_main(["ledger", path, "--html", "-o", out]), 0)
            with open(out, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("<!doctype html>"))


class AuditRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from gat.ifc_audit import audit_ifc_file

        cls.document = audit_ifc_file(MODEL).to_dict()

    def test_audit_format_constant_matches_the_audit_module(self) -> None:
        from gat.ifc_audit import AUDIT_FORMAT

        self.assertEqual(report.AUDIT_FORMAT, AUDIT_FORMAT)

    def test_ready_audit_renders_stages_products_and_assurance(self) -> None:
        decoded = report.decode_response(copy.deepcopy(self.document))
        self.assertEqual(decoded.operation, "audit")
        self.assertEqual(decoded.disposition, "PASS")
        text = report.render_text(decoded)
        self.assertIn("fail-closed IFC compatibility audit", text)
        self.assertIn("pipeline stages", text)
        self.assertIn("READY", text)
        self.assertIn("audit_authorizes_decisions        no", text)
        self.assertIn(report.NON_AUTHORIZING_FOOTER, text)
        html = report.render_html(decoded)
        self.assertNotIn("<script", html)
        self.assertIn(report.disposition_hex("PASS"), html)

    def test_readiness_claim_must_match_stage_statuses(self) -> None:
        tampered = copy.deepcopy(self.document)
        tampered["pipeline"]["lowering"]["status"] = "BLOCKED"
        with self.assertRaises(ValueError):
            report.decode_response(tampered)

    def test_audit_cli_emits_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "audit.html")
            self.assertEqual(cli_main(["audit", MODEL, "--html", "-o", out]), 0)
            with open(out, encoding="utf-8") as handle:
                content = handle.read()
            self.assertTrue(content.startswith("<!doctype html>"))
            self.assertIn("fail-closed IFC compatibility audit", content)

    def test_saved_audit_json_renders_through_gat_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.document, handle)
            self.assertEqual(cli_main(["report", path, "-o", os.devnull]), 0)


class CliReportTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> int:
        return cli_main(list(argv))

    def test_report_command_renders_and_exits_zero(self) -> None:
        response = handle_request(request("summary", {}))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "response.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(response, handle)
            self.assertEqual(self.run_cli("report", path, "-o", os.devnull), 0)
            out = os.path.join(tmp, "report.html")
            self.assertEqual(self.run_cli("report", path, "--html", "-o", out), 0)
            with open(out, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("<!doctype html>"))

    def test_error_response_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "error.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "format": report.RESPONSE_FORMAT,
                        "error": {"type": "ValueError", "message": "boom"},
                    },
                    handle,
                )
            self.assertEqual(self.run_cli("report", path, "-o", os.devnull), 1)

    def test_invalid_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"format": "not-a-response"}')
            self.assertEqual(self.run_cli("report", path), 2)


if __name__ == "__main__":
    unittest.main()
