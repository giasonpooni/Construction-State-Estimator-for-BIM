"""External record digests bind. They do not become beam evidence."""

from __future__ import annotations

import hashlib
import unittest

from gat.adapters.external_commitment import (
    bind_external_commitment,
    canonical_digest,
)


def _envelope(payload: dict, *, schema: str = "rci-evidence-commitment-v1", kind: str = "instrument-observation") -> dict:
    return {
        "schema": schema,
        "kind": kind,
        "claim_scope": "record-integrity-only",
        "observation_id": payload.get("observation_id"),
        "payload": payload,
        "digest": canonical_digest(payload),
    }


class ExternalCommitmentTests(unittest.TestCase):
    def test_recomputes_digest(self) -> None:
        payload = {
            "observation_id": "bench-1:1",
            "indicated": 2.0,
            "indicated_unit": "mm",
            "raw": 200.0,
        }
        bound = bind_external_commitment(_envelope(payload))
        self.assertEqual(bound.digest, canonical_digest(payload))
        self.assertFalse(bound.usable_as_calibrated_observation)
        self.assertEqual(len(bound.evidence_commitment_hex()), 64)

    def test_refuses_tampered_digest(self) -> None:
        payload = {"observation_id": "bench-1:1", "indicated": 2.0}
        document = _envelope(payload)
        document["digest"] = hashlib.sha256(b"nope").hexdigest()
        with self.assertRaisesRegex(ValueError, "digest"):
            bind_external_commitment(document)

    def test_refuses_beam_property_smuggling(self) -> None:
        payload = {
            "observation_id": "bench-1:1",
            "quantity": "YieldStrengthMPa",
            "indicated": 345.0,
        }
        with self.assertRaisesRegex(ValueError, "beam"):
            bind_external_commitment(_envelope(payload))

    def test_torus_report_schema_binds(self) -> None:
        payload = {"title": "first-release", "result": {"length": 4.123}}
        bound = bind_external_commitment(
            _envelope(payload, schema="torus-report-commitment-v1", kind="torus-report")
        )
        self.assertEqual(bound.schema, "torus-report-commitment-v1")
        self.assertFalse(bound.usable_as_calibrated_observation)


if __name__ == "__main__":
    unittest.main()
