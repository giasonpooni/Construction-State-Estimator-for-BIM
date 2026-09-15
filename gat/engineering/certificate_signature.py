"""Detachable HMAC identity for material-certificate bytes.

The certificate JSON schema stays exact-keys v1. A sibling ``.sig.json``
file binds those bytes to a named key. Unknown keys and bad MACs fail
closed. This is identity, not issuer accreditation.

There is no default trust store. ``keys`` is a required argument on both
signing and verification, and an empty store is refused rather than treated
as "trust nothing, silently". An earlier version fell back to
:func:`fixture_trust_store` when ``keys`` was omitted, which meant a caller who
forgot the argument would accept anything signed with the published test
secret below. That secret is in this file, in the repository, and in every
published copy of it: it authenticates nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path

from gat.errors import CertificateIngestionError


ALGORITHM = "hmac-sha256-v1"

#: The key used by this repository's own fixtures and demos. Its secret is
#: published here, so a MAC under it proves only that the bytes have not
#: changed since this repository signed them. Never put it in a trust store
#: that guards a real acceptance decision.
TEST_KEY_ID = "gat-test-cert-key-v1"
TEST_KEY_SECRET = b"gat-test-cert-key-v1-not-for-production"


@dataclass(frozen=True)
class CertificateSignature:
    key_id: str
    algorithm: str
    digest: str
    mac: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "digest": self.digest,
            "mac": self.mac,
        }


def fixture_trust_store() -> dict[str, bytes]:
    """The repository's own fixture key. Not a production trust store.

    Callers must pass this explicitly; nothing falls back to it.
    """
    return {TEST_KEY_ID: TEST_KEY_SECRET}


def _resolve(keys: dict[str, bytes] | None, action: str) -> dict[str, bytes]:
    if not keys:
        raise ValueError(
            f"{action} requires an explicit non-empty trust store; there is no "
            "default key set. Pass keys={key_id: secret}, or "
            "fixture_trust_store() for this repository's own fixtures."
        )
    return keys


def sign_certificate_bytes(
    source_bytes: bytes,
    *,
    key_id: str,
    keys: dict[str, bytes],
) -> CertificateSignature:
    secret = _resolve(keys, "signing").get(key_id)
    if secret is None:
        raise ValueError(f"unknown certificate key {key_id!r}")
    digest = hashlib.sha256(source_bytes).hexdigest()
    mac = hmac.new(secret, source_bytes, hashlib.sha256).hexdigest()
    return CertificateSignature(key_id, ALGORITHM, digest, mac)


def verify_certificate_bytes(
    source_bytes: bytes,
    signature: CertificateSignature | dict[str, str],
    *,
    keys: dict[str, bytes],
) -> bool:
    if isinstance(signature, dict):
        signature = CertificateSignature(
            signature["key_id"],
            signature["algorithm"],
            signature["digest"],
            signature["mac"],
        )
    trusted = _resolve(keys, "verification")
    if signature.algorithm != ALGORITHM:
        return False
    secret = trusted.get(signature.key_id)
    if secret is None:
        return False
    digest = hashlib.sha256(source_bytes).hexdigest()
    if not hmac.compare_digest(digest, signature.digest):
        return False
    expected = hmac.new(secret, source_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.mac)


def write_signature(path: str | Path, signature: CertificateSignature) -> None:
    Path(path).write_text(
        json.dumps(signature.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


#: Fields a signature document must carry to be one.
_SIGNATURE_FIELDS = ("key_id", "algorithm", "digest", "mac")


def read_signature(path: str | Path) -> CertificateSignature:
    """Read a signature document, refusing anything that is not one.

    This reader took an external file straight to ``json.loads`` and
    subscripted the result. Every way of getting it wrong came back as a
    Python builtin that named neither the file nor the field it wanted: a
    malformed document as ``JSONDecodeError``; ``null``, ``[]``, ``42`` and
    ``"hi"`` -- all legal JSON -- as ``TypeError: 'NoneType' object is not
    subscriptable``; ``{}`` as ``KeyError: 'key_id'``; and a deeply nested
    array as ``RecursionError``, since ``json`` recurses per level with no
    depth limit. None of them is a ``GatError``.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CertificateIngestionError(
            f"could not read certificate signature: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CertificateIngestionError(
            f"certificate signature is {type(payload).__name__}, not a JSON object"
        )
    missing = [field for field in _SIGNATURE_FIELDS if field not in payload]
    if missing:
        raise CertificateIngestionError(
            f"certificate signature is missing {missing}"
        )
    return CertificateSignature(*(payload[field] for field in _SIGNATURE_FIELDS))
