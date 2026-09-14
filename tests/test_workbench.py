"""The CSE Console: six readouts, one specimen, one identity.

The shell used to wear another project's identity -- a projection triad and
two selector positions reserved for libraries it does not contain. These
tests pin the instrument it is instead, including that the foreign names do
not come back.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

import gat.demo
from gat.cli import main as cli_main
from gat.geometry.viewer import decision_overlay, viewer_payload
from gat.report import (
    NON_AUTHORIZING_FOOTER,
    READ_ONLY_FOOTER,
    decode_ledger,
    decode_response,
    render_html,
    render_html_fragment,
)
from gat.session import GatSession
from gat.workbench import (
    AVAILABLE,
    EMPTY,
    MESSAGE_FORMAT,
    NOT_MEASURED,
    READOUTS,
    READOUT_SPEC_VERSION,
    EMPTY,
    CONSOLE_FORMAT,
    export_console_html,
    graph_payload,
    readout_specs,
    render_console_html,
    state_payload,
    console_payload,
)


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")
WALL_PARTY = "IfcWall:GATWAL0000000000000180"


def clearance_request(request_id: str = "duct-route-1") -> dict:
    return {
        "format": "gat-headless-request-v1",
        "request_id": request_id,
        "operation": "acceptance",
        "state": {"kind": "ifc", "path": MODEL},
        "payload": {
            "case_id": "route-1",
            "workflow": "AS_BUILT_CLEARANCE",
            "subject": "crossing duct",
            "checks": [
                {
                    "kind": "clearance",
                    "check_id": "route-clearance",
                    "proposal": {
                        "origin": [4.0, 1.8, 2.6],
                        "angle": 0.0,
                        "extents": [3.0, 0.4, 0.4],
                    },
                    "required_clearance": 0.05,
                    "confidence": 0.95,
                    "position_sigma": 0.02,
                    "label": "crossing duct",
                }
            ],
        },
    }


def build_ledger(tmp: str) -> str:
    from gat.causal import AssessmentRecord
    from gat.engine.transform import ShiftParameter

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


class ReadoutSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = GatSession.load_ifc(MODEL).world

    def specs(self, **bound):
        flags = {"decision_bound": False, "ledger_bound": False, "audit_bound": False}
        flags.update(bound)
        return readout_specs(self.world, **flags)

    def test_readouts_follow_the_order_an_operator_works_through(self) -> None:
        self.assertEqual(
            READOUTS,
            ("FIELD", "RELATIONS", "BELIEF", "LOG", "DECISION", "INTAKE"),
        )
        self.assertEqual(tuple(spec.readout for spec in self.specs()), READOUTS)

    def test_no_readout_names_a_third_party_product(self) -> None:
        """The instrument is described by what it reads, not by whose library
        would sit there."""
        for spec in self.specs():
            with self.subTest(readout=spec.readout):
                for foreign in ("kepler", "Cesium", "Three.js"):
                    self.assertNotIn(foreign, spec.instrument)
                    self.assertNotIn(foreign, spec.source)

    def test_limits_are_declared_once_not_as_dead_selector_positions(self) -> None:
        """An earlier shell carried MAP and GLOBE as permanently unavailable
        readouts. They were another product's silhouette, and a selector with
        knobs that never turn teaches an operator to distrust the ones that do."""
        self.assertNotIn("MAP", READOUTS)
        self.assertNotIn("GLOBE", READOUTS)
        limits = dict(NOT_MEASURED)
        self.assertIn("IfcSite", limits["geographic position"])
        self.assertIn("network", limits["geodetic reality"])
        self.assertIn("time series", limits["time"])

    def test_every_readout_on_the_selector_can_actually_read(self) -> None:
        for spec in self.specs():
            with self.subTest(readout=spec.readout):
                self.assertIn(spec.availability, (AVAILABLE, EMPTY))
                if spec.availability == EMPTY:
                    # EMPTY means nothing is bound yet, and says how to bind it.
                    self.assertTrue(spec.reason)

    def test_unbound_modes_are_empty_and_say_what_fills_them(self) -> None:
        by_mode = {spec.readout: spec for spec in self.specs()}
        for mode in ("FIELD", "RELATIONS", "BELIEF"):
            self.assertEqual(by_mode[mode].availability, AVAILABLE)
        self.assertEqual(by_mode["LOG"].availability, EMPTY)
        self.assertIn("--ledger", by_mode["LOG"].reason)
        self.assertEqual(by_mode["DECISION"].availability, EMPTY)
        self.assertIn("--decision", by_mode["DECISION"].reason)
        self.assertEqual(by_mode["INTAKE"].availability, EMPTY)
        bound = {
            spec.readout: spec
            for spec in self.specs(decision_bound=True, ledger_bound=True, audit_bound=True)
        }
        for mode in ("LOG", "DECISION", "INTAKE"):
            self.assertEqual(bound[mode].availability, AVAILABLE)
            self.assertEqual(bound[mode].reason, "")

    def test_every_mode_declares_its_loss_frame_and_time(self) -> None:
        for spec in self.specs(decision_bound=True, ledger_bound=True, audit_bound=True):
            for field in ("source", "transformation", "meaning", "loss", "identity",
                          "frame", "time"):
                self.assertTrue(getattr(spec, field), f"{spec.readout}.{field}")
        by_mode = {spec.readout: spec for spec in self.specs()}
        self.assertIn("marginals only", by_mode["BELIEF"].loss)
        self.assertIn("carry no information", by_mode["RELATIONS"].loss)
        self.assertIn("no geodetic frame", by_mode["FIELD"].frame)

    def test_spec_dict_declares_version_and_no_mutation(self) -> None:
        record = self.specs()[0].to_dict()
        self.assertEqual(record["version"], READOUT_SPEC_VERSION)
        self.assertIs(record["mutates_specimen"], False)
        self.assertEqual(
            set(record),
            {"version", "readout", "instrument", "question", "surface_class",
             "source", "transformation", "meaning", "loss", "identity", "frame",
             "time", "availability", "reason", "mutates_specimen"},
        )


class GraphPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = GatSession.load_ifc(MODEL).world
        cls.graph = graph_payload(cls.world)

    def test_layout_is_deterministic_and_bounded(self) -> None:
        self.assertEqual(self.graph, graph_payload(self.world))
        self.assertGreaterEqual(self.graph["rows"], 3)
        self.assertEqual(len(self.graph["row_classes"]), self.graph["rows"])
        for node in self.graph["nodes"]:
            self.assertLess(node["row"], self.graph["rows"])
            self.assertLess(node["column"], node["columns"])
            self.assertIn(node["class"], self.graph["row_classes"][node["row"]])

    def test_edges_are_typed_and_reference_known_nodes(self) -> None:
        ids = {node["entity"] for node in self.graph["nodes"]}
        self.assertEqual(len(self.graph["edges"]), len(self.world.module.rels))
        for edge in self.graph["edges"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)
            self.assertIn("source_ref", edge)
        self.assertEqual(
            sum(entry["count"] for entry in self.graph["kinds"]), len(self.graph["edges"])
        )
        self.assertEqual(
            [entry["kind"] for entry in self.graph["kinds"]],
            ["aggregates", "contains", "bounds", "voids", "fills"],
        )

    def test_containers_read_above_what_they_contain(self) -> None:
        row = {node["entity"]: node["row"] for node in self.graph["nodes"]}
        for edge in self.graph["edges"]:
            if edge["kind"] in ("aggregates", "contains"):  # container above content
                self.assertLess(row[edge["source"]], row[edge["target"]], edge)
            if edge["kind"] == "bounds":  # wall bounds space: the wall reads below
                self.assertGreater(row[edge["source"]], row[edge["target"]], edge)
            if edge["kind"] == "voids":  # opening voids wall: below the wall
                self.assertGreater(row[edge["source"]], row[edge["target"]], edge)
            if edge["kind"] == "fills":  # door fills opening: below the opening
                self.assertGreater(row[edge["source"]], row[edge["target"]], edge)


class StatePayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = GatSession.load_ifc(MODEL).world
        cls.state = state_payload(cls.world)

    def test_identity_survives_representation(self) -> None:
        state_ids = {entity["entity"] for entity in self.state["entities"]}
        graph_ids = {node["entity"] for node in graph_payload(self.world)["nodes"]}
        viewer_ids = {
            element["entity"] for element in viewer_payload(self.world, n=0)["elements"]
        }
        self.assertEqual(state_ids, graph_ids)
        self.assertTrue(viewer_ids <= state_ids)
        self.assertIn(WALL_PARTY, viewer_ids)
        self.assertEqual(self.state["world_digest"], self.world.digest())

    def test_quantities_carry_mean_sigma_role_and_unit(self) -> None:
        wall = next(e for e in self.state["entities"] if e["entity"] == WALL_PARTY)
        self.assertEqual(wall["name"], "Wall-Party")
        by_name = {q["name"]: q for q in wall["quantities"]}
        length = by_name["Length"]
        self.assertEqual(length["role"], "raw")
        self.assertEqual(length["unit"], "m")
        self.assertAlmostEqual(length["mean"], 4.0, places=2)
        self.assertGreater(length["sigma"], 0)
        volume = by_name["NetVolume"]
        self.assertEqual(volume["role"], "derived")
        self.assertEqual(volume["unit"], "m3")
        self.assertGreater(self.state["raw"], 0)
        self.assertGreater(self.state["derived"], 0)


class WorkbenchDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from gat.headless import handle_request
        from gat.ifc_audit import audit_ifc_file

        cls.world = GatSession.load_ifc(MODEL).world
        cls.request = clearance_request()
        cls.response = handle_request(cls.request)
        cls.decision = decision_overlay(cls.world, cls.response, cls.request)
        cls.decision_report = decode_response(cls.response)
        cls.audit = decode_response(audit_ifc_file(MODEL).to_dict())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ledger = decode_ledger(build_ledger(cls.tmp.name))
        cls.payload = console_payload(
            cls.world,
            model_name="model.ifc",
            n=2,
            decision=cls.decision,
            decision_report=cls.decision_report,
            ledger=cls.ledger,
            audit=cls.audit,
        )
        cls.html = render_console_html(
            cls.payload,
            decision_report=cls.decision_report,
            ledger=cls.ledger,
            audit=cls.audit,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_payload_is_deterministic_and_complete(self) -> None:
        again = console_payload(
            self.world,
            model_name="model.ifc",
            n=2,
            decision=self.decision,
            decision_report=self.decision_report,
            ledger=self.ledger,
            audit=self.audit,
        )
        self.assertEqual(self.payload, again)
        self.assertEqual(self.payload["format"], CONSOLE_FORMAT)
        self.assertEqual(self.payload["message_format"], MESSAGE_FORMAT)
        self.assertEqual([m["readout"] for m in self.payload["readouts"]], list(READOUTS))
        self.assertTrue(all(m["availability"] == AVAILABLE
                            for m in self.payload["readouts"] if m["readout"] not in ("MAP", "GLOBE")))
        self.assertEqual(self.payload["decision"]["disposition"], "REJECT")
        self.assertEqual(self.payload["decision"]["subjects"], ["Wall-Party"])
        self.assertEqual(self.payload["field"]["world_digest"], self.world.digest())

    def test_document_is_one_offline_file(self) -> None:
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertIn('sandbox="allow-scripts"', self.html)
        self.assertIn("srcdoc=", self.html)
        self.assertIn(CONSOLE_FORMAT, self.html)
        self.assertIn(MESSAGE_FORMAT, self.html)
        self.assertIn(READ_ONLY_FOOTER, self.html)
        self.assertIn(NON_AUTHORIZING_FOOTER, self.html)
        for rule in self.payload["rules"]:
            self.assertIn(rule, self.html)

    def test_every_mode_has_a_tab_and_a_panel(self) -> None:
        for mode in READOUTS:
            self.assertIn(f'role="tab" data-mode="{mode}"', self.html)
            self.assertIn(f'class="panel" data-mode="{mode}" role="tabpanel"', self.html)
        # The tab's class is the readout's availability, not a guess.
        for spec in self.payload["readouts"]:
            with self.subTest(readout=spec["readout"]):
                self.assertIn(
                    f'data-mode="{spec["readout"]}" class="{spec["availability"]}"',
                    self.html,
                )

    def test_the_shell_is_laid_out_as_an_instrument(self) -> None:
        for part in ('id="specimen"', 'id="modes"', 'id="panels"', 'id="reading"'):
            self.assertIn(part, self.html)
        self.assertIn("this instrument does not measure", self.html)
        self.assertIn("CSE Console", self.html)

    def test_the_shell_carries_no_other_project(self) -> None:
        for foreign in ("Notation", "kepler", "Cesium", "projection triad"):
            self.assertNotIn(foreign, self.html)

    def test_reports_compose_byte_identically(self) -> None:
        for report in (self.decision_report, self.ledger, self.audit):
            fragment = render_html_fragment(report)
            self.assertIn(fragment, self.html)
            self.assertIn(fragment, render_html(report))
        self.assertIn("hash chain verified", self.html)
        self.assertIn("REJECT", self.html)

    def test_decision_and_report_bind_together_or_not_at_all(self) -> None:
        with self.assertRaisesRegex(ValueError, "bound together"):
            console_payload(self.world, n=0, decision=self.decision)
        with self.assertRaisesRegex(ValueError, "bound together"):
            console_payload(self.world, n=0, decision_report=self.decision_report)
        with self.assertRaisesRegex(ValueError, "disagree"):
            console_payload(
                self.world, n=0, decision=self.decision, decision_report=self.ledger
            )

    def test_unbound_modes_state_their_reason_in_the_page(self) -> None:
        payload = console_payload(self.world, n=0, audit_reason="The IFC audit was skipped.")
        html = render_console_html(payload)
        self.assertIn("No decision is bound", html)
        self.assertIn("No execution ledger is bound", html)
        self.assertIn("The IFC audit was skipped.", html)
        self.assertIn('data-mode="LOG" class="empty"', html)
        self.assertIn("no decision bound", html)

    def test_structure_scene_carries_audit_statuses_only_with_the_audit(self) -> None:
        from gat.geometry.viewer import audit_statuses
        from gat.ifc_audit import audit_ifc_file

        statuses = audit_statuses(audit_ifc_file(MODEL).to_dict())
        payload = console_payload(self.world, n=0, audit=self.audit, audit_statuses=statuses)
        self.assertEqual(payload["field"]["audit"]["matched"], 8)
        field = next(r for r in payload["readouts"] if r["readout"] == "FIELD")
        self.assertIn("EXPLODE", field["transformation"])
        with self.assertRaisesRegex(ValueError, "bind both or neither"):
            console_payload(self.world, n=0, audit_statuses=statuses)

    def test_untrusted_names_are_escaped(self) -> None:
        payload = json.loads(json.dumps(console_payload(self.world, n=0)))
        payload["model"] = "<img src=x onerror=alert(1)>"
        html = render_console_html(payload)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)


class WorkbenchCliTests(unittest.TestCase):
    def test_cli_writes_the_instrument_with_every_binding(self) -> None:
        from gat.headless import handle_request

        request = clearance_request("cli-route")
        response = handle_request(request)
        with tempfile.TemporaryDirectory() as tmp:
            request_path = os.path.join(tmp, "request.json")
            response_path = os.path.join(tmp, "response.json")
            with open(request_path, "w", encoding="utf-8") as handle:
                json.dump(request, handle)
            with open(response_path, "w", encoding="utf-8") as handle:
                json.dump(response, handle)
            ledger_path = build_ledger(tmp)
            out = os.path.join(tmp, "workbench.html")
            self.assertEqual(
                cli_main(["workbench", MODEL, "-o", out, "--variations", "1",
                          "--decision", response_path, "--request", request_path,
                          "--ledger", ledger_path]),
                0,
            )
            with open(out, encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn('"disposition":"REJECT"', html)
            self.assertIn("hash chain verified", html)
            self.assertIn("gat-ifc-audit-v1", html)
            self.assertIn("&quot;audit&quot;:{&quot;status&quot;:&quot;READY&quot;", html)
            self.assertNotIn("No decision is bound", html)
            # --request without --decision has nothing to bind: refused
            self.assertEqual(
                cli_main(["workbench", MODEL, "-o", out, "--request", request_path]), 2
            )

    def test_cli_no_audit_leaves_complexity_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "workbench.html")
            self.assertEqual(
                cli_main(["workbench", MODEL, "-o", out, "--variations", "0", "--no-audit"]), 0
            )
            with open(out, encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn("--no-audit", html)
            self.assertIn('data-mode="INTAKE" class="empty"', html)
            self.assertIn("No decision is bound", html)

    def test_cli_refuses_a_tampered_ledger_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = build_ledger(tmp)
            with open(ledger_path, encoding="utf-8") as handle:
                document = json.load(handle)
            document["events"][1]["operation"]["delta"] = 0.5
            with open(ledger_path, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
            out = os.path.join(tmp, "workbench.html")
            self.assertEqual(
                cli_main(["workbench", MODEL, "-o", out, "--variations", "0",
                          "--ledger", ledger_path]),
                2,
            )
            self.assertFalse(os.path.exists(out))

    def test_export_returns_availability_per_mode(self) -> None:
        world = GatSession.load_ifc(MODEL).world
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "workbench.html")
            availability = export_console_html(world, out, n=0)
            self.assertTrue(os.path.exists(out))
        self.assertEqual(list(availability), list(READOUTS))
        self.assertEqual(availability["FIELD"], AVAILABLE)
        self.assertEqual(availability["LOG"], EMPTY)


class WalkthroughDemoTests(unittest.TestCase):
    def test_clearance_walkthrough_is_self_asserting(self) -> None:
        from gat.demo.workbench import run

        with tempfile.TemporaryDirectory() as tmp:
            result = run(tmp)
            self.assertEqual(result["disposition"], "REJECT")
            for name in ("request.json", "response.json", "ledger.json", "workbench.html"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)
            with open(result["page"], encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn("hash chain verified", html)
            self.assertIn('data-mode="DECISION" class="available"', html)


if __name__ == "__main__":
    unittest.main()


class PayloadWeightTests(unittest.TestCase):
    """The scene is embedded in the viewer frame; it must not ride along in
    the data block too. The readout rename moved the payload key from
    "structure" to "field" and left the strip filter on the old name, so the
    whole scene was serialized twice and the page grew ~60%."""

    def test_the_data_block_does_not_repeat_the_scene(self) -> None:
        world = GatSession.load_ifc(MODEL).world
        payload = console_payload(world, model_name="model.ifc", n=4)
        html = render_console_html(payload)
        start = html.index('<script id="console-data"')
        block = html[start : html.index("</script>", start)]
        self.assertNotIn('"field"', block)
        self.assertLess(
            len(block),
            len(json.dumps(payload["field"])),
            "the data block is smaller than the scene it must not contain",
        )

    def test_the_viewer_frame_still_has_it(self) -> None:
        """Stripping it from the data block must not strip it from the page."""
        from gat.geometry.viewer import VIEWER_SCENE_FORMAT

        world = GatSession.load_ifc(MODEL).world
        html = render_console_html(console_payload(world, model_name="m", n=2))
        srcdoc = html[html.index('<iframe id="structure"') :]
        self.assertIn(VIEWER_SCENE_FORMAT, srcdoc)
