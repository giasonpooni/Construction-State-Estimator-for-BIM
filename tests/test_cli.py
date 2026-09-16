"""The ``gat`` command line: exit codes, JSON output, artifacts."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from gat.cli import main

MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gat", "demo", "model.ifc",
)


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_verify_passes_on_demo(self) -> None:
        code, out, _ = run_cli("verify", MODEL)
        self.assertEqual(code, 0)
        self.assertIn("compliance:", out)

    def test_verify_json_is_parseable(self) -> None:
        code, out, _ = run_cli("verify", MODEL, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["passed"])
        self.assertEqual(data["invariants"]["fail"], 0)

    def test_check_clean_model_exits_zero(self) -> None:
        code, out, _ = run_cli("check", MODEL)
        self.assertEqual(code, 0)
        self.assertIn("clash report:", out)

    def test_check_crossing_duct_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "duct.json")
            with open(spec, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "origin": [4.0, 1.8, 2.6],
                        "extents": [3.0, 0.4, 0.4],
                        "angle_deg": 0.0,
                        "position_sigma": 0.02,
                    },
                    fh,
                )
            code, out, _ = run_cli("check", MODEL, "--proposed", spec, "--json")
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertGreater(data["worst_p_clash"], 0.999)
            self.assertEqual(data["proposed"][0]["a"], "Wall-Party")

    def test_check_rerouted_duct_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "duct.json")
            with open(spec, "w", encoding="utf-8") as fh:
                json.dump(
                    {"origin": [4.0, 1.8, 3.55], "extents": [3.0, 0.4, 0.4]}, fh
                )
            code, out, _ = run_cli("check", MODEL, "--proposed", spec, "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["proposed"], [])

    def test_inspect_summary_and_variable(self) -> None:
        code, out, _ = run_cli("inspect", MODEL, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["n_raw"], 24)

        code, out, _ = run_cli("inspect", MODEL, "--var", "Level 1.TotalWallCost")
        self.assertEqual(code, 0)
        self.assertIn("8503.2", out)
        self.assertIn("Wall-South.Width", out)  # pretty-printed sensitivity

    def test_inspect_bad_var_syntax_exits_two(self) -> None:
        code, _, err = run_cli("inspect", MODEL, "--var", "NoDotHere")
        self.assertEqual(code, 2)
        self.assertIn("Entity-Name.Quantity", err)

    def test_splats_with_variations_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli(
                "splats", MODEL, tmp, "--variations", "3", "--seed", "5"
            )
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "building.ply")))
            with open(os.path.join(tmp, "building.ply"), "rb") as fh:
                self.assertTrue(fh.read(3) == b"ply")
            manifest_path = os.path.join(tmp, "manifest.json")
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            self.assertEqual(manifest["n"], 3)
            for sample in manifest["samples"]:
                self.assertTrue(os.path.exists(os.path.join(tmp, sample["file"])))

    def test_variations_are_seed_deterministic(self) -> None:
        import filecmp

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            run_cli("splats", MODEL, a, "--variations", "2", "--seed", "9")
            run_cli("splats", MODEL, b, "--variations", "2", "--seed", "9")
            for name in ("variation_000.ply", "variation_001.ply", "manifest.json"):
                self.assertTrue(
                    filecmp.cmp(
                        os.path.join(a, name), os.path.join(b, name), shallow=False
                    ),
                    name,
                )

    def test_sample_json(self) -> None:
        code, out, _ = run_cli("sample", MODEL, "--n", "100", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["n"], 100)
        self.assertGreaterEqual(data["pass_rate"], 0.9)

    def test_missing_model_exits_two(self) -> None:
        code, _, err = run_cli("verify", "/nonexistent/model.ifc")
        self.assertEqual(code, 2)
        self.assertIn("gat:", err)

    def test_bad_usage_exits_two(self) -> None:
        code, _, _ = run_cli("frobnicate")
        self.assertEqual(code, 2)


class ProposedSpecIsRefusedNotGuessedTests(unittest.TestCase):
    """``gat check --proposed`` cleared a duct that goes through a wall, and
    tracebacked on a misshapen spec.

    _run_check built the OrientedBox straight out of the JSON -- ``tuple(
    spec["origin"])``, ``float(spec.get("angle_deg", 0.0))`` -- and called
    score_proposed_box, which checked nothing either. Two consequences,
    both measured on gat/demo/model.ifc before the fix.

    Wrong answer: origin (4.0, 1.8, 2.6) extents (3.0, 0.4, 0.4) exits 1
    with "clearance -0.4000 P(clash) 1.0000". The mirrored spelling of the
    SAME occupied region -- origin (7.0, 2.2, 3.0) extents
    (-3.0, -0.4, -0.4), identical centre [5.5, 2.0, 2.8] and identical AABB
    [4, 1.8, 2.6]-[7, 2.2, 3.0], straight through Wall-Party -- exited 0
    with "clearance +1.8000 P(clash) 0.0000" and overlap mass -0.02955 m3.
    Extents (0, 0, 0) exited 0 with zero proposed items. The declared type
    for this question, ClearanceDecision, refuses all of them with
    "proposed box extents must be positive"; the CLI called past it.

    Tracebacks: a JSON array exited 1 with TypeError, a 2-element "extents"
    with IndexError, ``"angle_deg": null`` with TypeError -- exit 1 being
    the code the module docstring reserves for a finding about the
    building, with empty stdout.
    """

    def _check(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "duct.json")
            with open(spec, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            return run_cli("check", MODEL, "--proposed", spec, "--json")

    def test_the_mirrored_duct_does_not_exit_zero(self):
        code, out, err = self._check(
            {"origin": [7.0, 2.2, 3.0], "extents": [-3.0, -0.4, -0.4],
             "angle_deg": 0.0, "position_sigma": 0.02}
        )
        self.assertEqual(code, 2)
        self.assertIn("gat: proposed box extents must be positive", err)
        self.assertEqual(out, "")

    def test_zero_extents_are_refused(self):
        code, _, err = self._check(
            {"origin": [4.0, 1.8, 2.6], "extents": [0.0, 0.0, 0.0]}
        )
        self.assertEqual(code, 2)
        self.assertIn("extents must be positive", err)

    def test_a_negative_position_sigma_is_refused(self):
        code, _, err = self._check(
            {"origin": [4.0, 1.8, 2.6], "extents": [3.0, 0.4, 0.4],
             "position_sigma": -0.02}
        )
        self.assertEqual(code, 2)
        self.assertIn("position_sigma", err)

    def test_misshapen_specs_refuse_by_name_without_a_traceback(self):
        cases = {
            "array instead of object": [1, 2, 3],
            "two extents": {"origin": [0, 0, 0], "extents": [1, 1]},
            "null angle": {"origin": [0, 0, 0], "extents": [1, 1, 1],
                           "angle_deg": None},
            "string extent": {"origin": [0, 0, 0], "extents": ["a", 1, 1]},
            "missing extents": {"origin": [0, 0, 0]},
            "nan origin": {"origin": [float("nan"), 0, 0], "extents": [1, 1, 1]},
        }
        for label, payload in cases.items():
            with self.subTest(spec=label):
                code, out, err = self._check(payload)
                self.assertEqual(code, 2)
                self.assertIn("gat:", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(out, "")

    def test_the_well_formed_spec_still_finds_the_clash(self):
        code, out, _ = self._check(
            {"origin": [4.0, 1.8, 2.6], "extents": [3.0, 0.4, 0.4],
             "angle_deg": 0.0, "position_sigma": 0.02}
        )
        self.assertEqual(code, 1)
        self.assertGreater(json.loads(out)["worst_p_clash"], 0.999)


class ClearanceWindowRefusesOnBothPathsTests(unittest.TestCase):
    """One flag, one value, one invocation, two opposite dispositions.

    ``--max-clearance`` fed both detect() and score_proposed_box(). The
    latter guarded it; the former did not. Measured before the fix:
    ``gat check gat/demo/model.ifc --max-clearance -1 --json`` printed
    worst_p_clash 0.0 with empty existing_pairs and exited 0 ("clash
    report: 0 scored pairs (0 past broad phase of 15)"), while the default
    run scores 6 pairs with worst p_clash 0.0317. Adding --proposed to that
    same command exited 2 with "gat: max_clearance must be non-negative or
    None". -0.01 was already the whole cliff: 6 scored pairs -> 0.
    """

    def test_a_negative_window_exits_two_with_and_without_proposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "duct.json")
            with open(spec, "w", encoding="utf-8") as fh:
                json.dump({"origin": [4.0, 1.8, 2.6],
                           "extents": [3.0, 0.4, 0.4]}, fh)
            for value in ("-0.01", "-1"):
                for extra in ((), ("--proposed", spec)):
                    with self.subTest(value=value, proposed=bool(extra)):
                        code, out, err = run_cli(
                            "check", MODEL, "--max-clearance", value, *extra
                        )
                        self.assertEqual(code, 2)
                        self.assertIn("max_clearance must be non-negative", err)
                        self.assertEqual(out, "")

    def test_a_non_finite_window_is_refused_at_parse_time(self):
        for value in ("nan", "inf"):
            with self.subTest(value=value):
                code, _, err = run_cli("check", MODEL, "--max-clearance", value)
                self.assertEqual(code, 2)
                self.assertIn("--max-clearance", err)

    def test_zero_is_still_a_valid_window(self):
        code, out, _ = run_cli("check", MODEL, "--max-clearance", "0", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["existing_pairs"]), 6)

    def test_a_non_finite_fail_above_cannot_swallow_a_certain_clash(self):
        # worst >= nan is False for every p_clash, so --fail-above nan
        # exited 0 on P(clash) 1.0000.
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "duct.json")
            with open(spec, "w", encoding="utf-8") as fh:
                json.dump({"origin": [4.0, 1.8, 2.6],
                           "extents": [3.0, 0.4, 0.4]}, fh)
            code, _, err = run_cli(
                "check", MODEL, "--proposed", spec, "--fail-above", "nan"
            )
            self.assertEqual(code, 2)
            self.assertIn("--fail-above", err)


class NoBuiltinReachesTheExitCodeTests(unittest.TestCase):
    """Five builtin exception types escaped main() across eight scenarios,
    each exiting 1 with a traceback and empty stdout.

    main() caught FileNotFoundError plus (GatError, KeyError, ValueError,
    JSONDecodeError), so a directory where a file belongs raised
    IsADirectoryError past all of them (``verify``/``check``/``inspect``/
    ``sample`` via _load, ``view``/``console`` via -o, ``view --decision``);
    ``splats model.ifc <an existing plain file>`` raised FileExistsError
    from os.makedirs; ``--spacing 0`` raised ZeroDivisionError inside
    ``extents[i] / spacing``. Exit 1 is the code the module docstring
    reserves for a finding -- a likely clash, a failed verification -- so an
    automated consumer branching on the code alone was handed a fabricated
    finding where the answer was "your input is wrong, exit 2". The control
    case was already right: a missing model exits 2 with one line.

    ``--spacing -1`` was worse than a crash: it exited 0, having tiled every
    box to a single primitive via ``max(1, ceil(extent / -1))``.
    """

    def _assert_refused(self, code, err, expect=2):
        self.assertEqual(code, expect)
        self.assertNotIn("Traceback", err)
        self.assertTrue(err.strip(), "a refusal must say something")

    def test_a_directory_where_a_file_belongs_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = os.path.join(tmp, "v.html")
            cases = {
                "verify model": ("verify", tmp),
                "check model": ("check", tmp),
                "inspect model": ("inspect", tmp),
                "sample model": ("sample", tmp),
                "view output": ("view", MODEL, "-o", tmp),
                "view decision": ("view", MODEL, "-o", html, "--decision", tmp),
                "console output": ("console", MODEL, "-o", tmp),
            }
            for label, argv in cases.items():
                with self.subTest(case=label):
                    code, out, err = run_cli(*argv)
                    self._assert_refused(code, err)
                    self.assertIn("gat:", err)
                    self.assertEqual(out, "")

    def test_splats_onto_an_existing_file_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "not-a-dir")
            with open(plain, "w", encoding="utf-8") as fh:
                fh.write("")
            code, _, err = run_cli("splats", MODEL, plain)
            self._assert_refused(code, err)
            self.assertIn("gat:", err)

    def test_a_spacing_that_is_not_a_length_is_refused_at_parse_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = os.path.join(tmp, "v.html")
            for command in (
                ("view", MODEL, "-o", html),
                ("console", MODEL, "-o", html),
                ("splats", MODEL, os.path.join(tmp, "out")),
            ):
                for value in ("0", "-1", "nan"):
                    with self.subTest(command=command[0], spacing=value):
                        code, _, err = run_cli(*command, "--spacing", value)
                        self._assert_refused(code, err)
                        self.assertIn("--spacing", err)

    def test_an_undeclared_exception_exits_three_not_one(self):
        # Exit 1 means a finding about the building. Anything that is
        # neither a refusal nor a finding gets its own code and keeps its
        # traceback, per gat.errors: the CLI is the must-not-miss caller.
        import gat.cli

        def boom(path):
            raise RuntimeError("synthetic defect")

        original = gat.cli._load
        gat.cli._load = boom
        try:
            code, out, err = run_cli("verify", MODEL)
        finally:
            gat.cli._load = original
        self.assertEqual(code, 3)
        self.assertIn("gat: internal error: RuntimeError: synthetic defect", err)
        self.assertIn("Traceback", err)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
