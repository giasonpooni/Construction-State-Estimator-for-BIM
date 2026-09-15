"""Certificate bytes can be believed or refused by a named key.

There is no default trust store. An earlier version of this module fell back
to the repository's own fixture key when `keys` was omitted, so a caller who
forgot the argument would have accepted anything signed with a secret that is
published in the source file. Both signing and verification now require the
store to be named.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import gat.demo
from gat.engineering.certificate_signature import (
    TEST_KEY_ID,
    CertificateSignature,
    read_signature,
    sign_certificate_bytes,
    fixture_trust_store,
    verify_certificate_bytes,
    write_signature,
)
from gat.errors import CertificateIngestionError
from gat.engineering.material_certificate import read_material_certificate


CERTIFICATE = Path(gat.demo.__file__).parent / "material_certificate.json"


class CertificateSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = CERTIFICATE.read_bytes()
        self.keys = fixture_trust_store()
        self.signature = sign_certificate_bytes(
            self.body, key_id=TEST_KEY_ID, keys=self.keys
        )

    def test_the_named_key_accepts_its_own_mac(self) -> None:
        self.assertEqual(self.signature.key_id, TEST_KEY_ID)
        self.assertTrue(
            verify_certificate_bytes(self.body, self.signature, keys=self.keys)
        )

    def test_altered_bytes_are_refused(self) -> None:
        self.assertFalse(
            verify_certificate_bytes(self.body + b" ", self.signature, keys=self.keys)
        )

    def test_a_different_trust_store_does_not_know_the_key(self) -> None:
        self.assertFalse(
            verify_certificate_bytes(
                self.body, self.signature, keys={"other": b"nope"}
            )
        )

    def test_the_signature_digest_matches_the_certificate(self) -> None:
        certificate = read_material_certificate(CERTIFICATE)
        self.assertEqual(certificate.source_digest, self.signature.digest)


class TrustStoreIsRequiredTests(unittest.TestCase):
    """Forgetting the trust store must be an error, never a silent default."""

    def setUp(self) -> None:
        self.body = CERTIFICATE.read_bytes()
        self.signature = sign_certificate_bytes(
            self.body, key_id=TEST_KEY_ID, keys=fixture_trust_store()
        )

    def test_verification_without_a_store_is_a_type_error(self) -> None:
        with self.assertRaises(TypeError):
            verify_certificate_bytes(self.body, self.signature)

    def test_signing_without_a_store_is_a_type_error(self) -> None:
        with self.assertRaises(TypeError):
            sign_certificate_bytes(self.body, key_id=TEST_KEY_ID)

    def test_an_empty_store_is_refused_rather_than_trusting_nothing_quietly(
        self,
    ) -> None:
        for keys in ({}, None):
            with self.subTest(keys=keys):
                with self.assertRaisesRegex(ValueError, "non-empty trust store"):
                    verify_certificate_bytes(self.body, self.signature, keys=keys)
                with self.assertRaisesRegex(ValueError, "non-empty trust store"):
                    sign_certificate_bytes(self.body, key_id=TEST_KEY_ID, keys=keys)

    def test_an_unknown_key_id_is_refused_not_raised(self) -> None:
        """A store that simply does not know the key is a refusal, not an error."""
        self.assertFalse(
            verify_certificate_bytes(
                self.body, self.signature, keys={"someone-else": b"secret"}
            )
        )

    def test_the_fixture_key_is_labelled_as_such(self) -> None:
        store = fixture_trust_store()
        self.assertEqual(list(store), [TEST_KEY_ID])
        self.assertIn(b"not-for-production", store[TEST_KEY_ID])


class HostileSignatureDocumentTests(unittest.TestCase):
    """A signature file comes from outside; reading one must not raise builtins.

    ``read_signature`` took the path straight to ``json.loads`` and
    subscripted the result, so every way of getting it wrong named neither
    the file nor the field: a malformed document as ``JSONDecodeError``;
    ``null``, ``[]``, ``42`` and ``"hi"`` -- all legal JSON -- as ``TypeError:
    'NoneType' object is not subscriptable``; ``{}`` as ``KeyError:
    'key_id'``; and a nested array as ``RecursionError``, since ``json``
    recurses per level with no depth limit. Nine of nine escaped the declared
    hierarchy.
    """

    HOSTILE = {
        "empty": "",
        "not json": "{{{",
        "json null": "null",
        "json array": "[]",
        "json number": "42",
        "json string": '"hi"',
        "empty object": "{}",
        "partial object": '{"key_id": "k"}',
        "deeply nested": "[" * 100_000 + "]" * 100_000,
    }

    def test_every_malformed_document_is_a_declared_refusal(self) -> None:
        for label, text in self.HOSTILE.items():
            with self.subTest(document=label):
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "sig.json")
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(text)
                    with self.assertRaises(CertificateIngestionError):
                        read_signature(path)

    def test_a_missing_file_is_a_declared_refusal_too(self) -> None:
        with self.assertRaises(CertificateIngestionError):
            read_signature("/nonexistent/none.json")

    def test_an_honest_signature_still_reads(self) -> None:
        signature = CertificateSignature(
            key_id="k1", algorithm="hmac-sha256", digest="d" * 64, mac="m" * 64
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "sig.json")
            write_signature(path, signature)
            self.assertEqual(read_signature(path), signature)


if __name__ == "__main__":
    unittest.main()
