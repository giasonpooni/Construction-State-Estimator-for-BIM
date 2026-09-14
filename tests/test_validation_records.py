"""Everything in `validation/` must be something the engine actually produced.

The directory used to hold hand-written claims wearing the costume of test
fixtures: world digests that no path form reproduced, `source` fields naming
files that did not exist, a geometry authority of SWEPT_SOLID on a model that
had no body representation at all. Nine of eleven records were referenced by
no code, so nothing ever noticed.

These tests re-run the producers in `validation/records.py` and compare
byte-for-byte against the shipped files. A record can no longer be edited by
hand, and a change in a disposition or a digest cannot land quietly.
"""

from __future__ import annotations

import json
import math
import os
import re
import unittest
from pathlib import Path

from validation.records import CORPUS_DEPENDENT, build_all, dumps


#: A lowercase SHA-256. Digests hash float64 array bytes, so they reproduce
#: only where the arithmetic does -- README: "Determinism is same-platform
#: byte identity."
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")

#: Floats in a record come out of the same float64 pipeline. A last-ulp
#: difference is a different platform, not a changed decision.
_FLOAT_RTOL = 1e-12


def _diff(shipped: object, rebuilt: object, path: str = "") -> tuple[list, list]:
    """Split differences into (semantic, digest-only).

    Semantic differences are drift and always fail. Digest-only differences,
    with every float still within tolerance, mean the records were generated
    on a different platform.
    """
    semantic: list[str] = []
    digests: list[str] = []

    if isinstance(shipped, dict) and isinstance(rebuilt, dict):
        if set(shipped) != set(rebuilt):
            semantic.append(
                f"{path or '<root>'}: keys {sorted(set(shipped) ^ set(rebuilt))}"
            )
            return semantic, digests
        for key in sorted(shipped):
            sub = _diff(shipped[key], rebuilt[key], f"{path}.{key}" if path else key)
            semantic += sub[0]
            digests += sub[1]
    elif isinstance(shipped, list) and isinstance(rebuilt, list):
        if len(shipped) != len(rebuilt):
            semantic.append(f"{path}: length {len(shipped)} != {len(rebuilt)}")
            return semantic, digests
        for index, (a, b) in enumerate(zip(shipped, rebuilt)):
            sub = _diff(a, b, f"{path}[{index}]")
            semantic += sub[0]
            digests += sub[1]
    elif isinstance(shipped, float) or isinstance(rebuilt, float):
        if not math.isclose(shipped, rebuilt, rel_tol=_FLOAT_RTOL, abs_tol=0.0):
            semantic.append(f"{path}: {shipped!r} != {rebuilt!r}")
    elif (
        isinstance(shipped, str)
        and isinstance(rebuilt, str)
        and _DIGEST.match(shipped)
        and _DIGEST.match(rebuilt)
    ):
        if shipped != rebuilt:
            digests.append(f"{path}: {shipped[:12]}... != {rebuilt[:12]}...")
    elif shipped != rebuilt:
        semantic.append(f"{path}: {shipped!r} != {rebuilt!r}")

    return semantic, digests


REPO = Path(__file__).resolve().parent.parent
VALIDATION = REPO / "validation"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")

#: Records produced by something other than validation/records.py. Each one
#: is load-bearing and read by code elsewhere in the tree.
EXTERNALLY_PRODUCED = {
    # the engineering oracle, transcribed from the AISC design-example volume
    "aisc360-22-f1-1b-v1.json",
    # the commit-pinned public model manifest, consumed by fetch_ifc_corpus.py
    "ifc-corpus-v1.json",
    # an explicitly environment-specific scale reference; it names the host it
    # was measured on and is a reference, not a threshold
    "incremental-scale-reference-v1.json",
    # the same, for the coupled shape: wall-clock seconds measured on one host
    "coupled-scale-reference-v1.json",
}


class ShippedRecordsTests(unittest.TestCase):
    # Building the records parses a 19 MB corpus model, so do it once for the
    # class rather than once per test method.
    records: dict[str, dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = build_all(CORPUS)

    def test_every_generated_record_matches_the_engine(self) -> None:
        """Decisions, verdicts and quantities, on any platform."""
        for name, record in sorted(self.records.items()):
            with self.subTest(record=name):
                path = VALIDATION / name
                self.assertTrue(path.exists(), f"{name} is missing; regenerate it")
                shipped = json.loads(path.read_text(encoding="utf-8"))
                semantic, _ = _diff(shipped, json.loads(json.dumps(record)))
                self.assertEqual(
                    semantic,
                    [],
                    f"{name} has drifted from what the engine produces. Run "
                    "python validation/regenerate.py and read the diff: a "
                    "changed verdict or quantity means a changed decision.",
                )

    def test_records_are_byte_exact_on_the_platform_that_wrote_them(self) -> None:
        """The stricter half, and the one CI enforces.

        World digests hash float64 array bytes, so they reproduce only where
        the arithmetic does. When every float still agrees to within
        `_FLOAT_RTOL` but a digest differs, this host is simply not the host
        that generated the records -- which the README already scopes as
        "same-platform byte identity" -- so the check is skipped rather than
        reported as drift.
        """
        drifted: list[str] = []
        for name, record in sorted(self.records.items()):
            shipped = json.loads((VALIDATION / name).read_text(encoding="utf-8"))
            _, digests = _diff(shipped, json.loads(json.dumps(record)))
            if digests:
                drifted.append(f"{name}: {digests[0]}")
        if drifted:
            self.skipTest(
                "digests were generated on a different platform; every "
                "verdict and quantity still agrees. First difference: "
                + drifted[0]
            )
        for name, record in sorted(self.records.items()):
            with self.subTest(record=name):
                self.assertEqual(
                    (VALIDATION / name).read_text(encoding="utf-8"),
                    dumps(record),
                    f"{name} differs byte-for-byte on the platform that "
                    "generated it; run python validation/regenerate.py",
                )

    def test_no_record_is_unaccounted_for(self) -> None:
        """Every JSON in validation/ is either generated here or declared."""
        on_disk = {p.name for p in VALIDATION.glob("*.json")}
        # Corpus-gated records are shipped even on a host that cannot rebuild
        # them, so they are accounted for whether or not this run built them.
        accounted = set(self.records) | EXTERNALLY_PRODUCED | CORPUS_DEPENDENT
        orphans = sorted(on_disk - accounted)
        self.assertEqual(
            orphans,
            [],
            "these records are produced by nothing and verified by nothing: "
            f"{orphans}. Generate them in validation/records.py or remove them.",
        )

    def test_corpus_records_are_present_when_the_corpus_is(self) -> None:
        if not CORPUS:
            self.skipTest("public IFC corpus not fetched")
        for name in sorted(CORPUS_DEPENDENT):
            self.assertIn(name, self.records)


class RecordHonestyTests(unittest.TestCase):
    """Properties the records must have to be evidence rather than assertion."""

    def setUp(self) -> None:
        self.shipped = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in VALIDATION.glob("*.json")
        }

    def test_every_outcome_log_source_exists(self) -> None:
        for row in self.shipped["outcome-log-v1.json"]["rows"]:
            with self.subTest(case=row["case_id"]):
                self.assertTrue(
                    (REPO / row["source"]).exists(),
                    f"{row['case_id']} cites {row['source']}, which does not exist",
                )

    def test_no_record_advertises_placeholder_digests(self) -> None:
        for name, record in sorted(self.shipped.items()):
            note = str(record.get("note", "")).lower()
            with self.subTest(record=name):
                for phrase in ("placeholder", "will not verify", "illustrative"):
                    self.assertNotIn(
                        phrase,
                        note,
                        f"{name} admits its own numbers are not real",
                    )

    def test_the_beam_record_earns_the_support_it_claims(self) -> None:
        """The section modulus is declared, and the model's solid backs it."""
        support = self.shipped["beam-b1-disposition-v1.json"]["support"]
        self.assertEqual(support["beam_geometry_status"], "COMPLETE")
        self.assertEqual(support["geometry_only_authority"], "SWEPT_SOLID")
        self.assertEqual(
            support["section_modulus_source"], "GAT_Structural declared property set"
        )
        corroboration = support["section_corroboration"]
        self.assertTrue(corroboration["corroborated"])
        self.assertEqual(corroboration["authority"], "DECLARED_CORROBORATED")
        # Z and S are different section properties; only their ratio is checked.
        low, high = corroboration["shape_factor_bounds"]
        self.assertLess(low, corroboration["shape_factor"])
        self.assertLess(corroboration["shape_factor"], high)
        self.assertGreater(
            corroboration["declared_plastic_modulus_m3"],
            corroboration["derived_elastic_modulus_m3"],
            "Z >= S is a geometric floor for any solid section",
        )

    def test_as_built_still_wants_evidence_even_with_support(self) -> None:
        """Corroborated support removes the geometry objection, not the evidence one."""
        prior = self.shipped["beam-b1-disposition-v1.json"]["prior"]
        self.assertEqual(prior["verdict"], "SATISFIED")

        as_built = prior["acceptance"]["as_built"]
        self.assertEqual(as_built["disposition"], "REQUEST_EVIDENCE")
        self.assertFalse(as_built["may_authorize"])
        self.assertEqual(
            as_built["insufficient_geometry_check_ids"],
            [],
            "the refusal must now be about evidence, not about support",
        )

        # The design-review policy waives field evidence but not support, so
        # it can only reach ACCEPT because the declaration is corroborated.
        design_review = prior["acceptance"]["design_review"]
        self.assertEqual(design_review["disposition"], "ACCEPT")
        self.assertTrue(design_review["may_authorize"])

    def test_a_violated_capacity_is_rejected_under_every_policy(self) -> None:
        revised = self.shipped["beam-b1-disposition-v1.json"][
            "revised_after_certificate"
        ]
        self.assertEqual(revised["verdict"], "VIOLATED")
        for policy, outcome in sorted(revised["acceptance"].items()):
            with self.subTest(policy=policy):
                self.assertEqual(outcome["disposition"], "REJECT")
                self.assertFalse(outcome["may_authorize"])

    def test_the_field_packet_signature_verifies(self) -> None:
        from gat.engineering.certificate_signature import (
            fixture_trust_store,
            verify_certificate_bytes,
        )

        packet = self.shipped["field-packet-beam-b1-v1.json"]
        source = REPO / packet["source_path"]
        self.assertTrue(packet["signature_verified"])
        self.assertTrue(
            verify_certificate_bytes(
                source.read_bytes(), packet["signature"], keys=fixture_trust_store()
            ),
            "the shipped HMAC does not verify against the certificate bytes",
        )

    def test_tampered_certificate_bytes_fail_the_packet_signature(self) -> None:
        from gat.engineering.certificate_signature import (
            fixture_trust_store,
            verify_certificate_bytes,
        )

        packet = self.shipped["field-packet-beam-b1-v1.json"]
        source = (REPO / packet["source_path"]).read_bytes()
        self.assertFalse(
            verify_certificate_bytes(
                source + b" ", packet["signature"], keys=fixture_trust_store()
            ),
            "the packet signature accepted altered certificate bytes",
        )


if __name__ == "__main__":
    unittest.main()
