"""Export an acceptance disposition as BCF 2.1, the format the industry reads.

A CSE disposition and a BCF topic are already almost the same object: an
``evidence_request`` names a check, a target, an action and a reason, which is a
BCF topic with a title, a description and a status. Exporting it means a
disposition can be opened in Solibri, Navisworks, BIMcollab or Revit by somebody
who did not produce it -- the second consumer this runtime has never had.

Two properties are kept that a generic BCF writer would lose.

*Replay.* Topic GUIDs are derived, not generated, so exporting the same
disposition twice produces byte-identical markup. Nothing here reads a clock:
BCF requires a creation date, so the caller supplies one. CSE does not invent
time any more than it invents evidence.

*Portability, and which identity a GUID rests on.* A topic GUID derived from
``case_digest`` is machine-local, because ``case_digest`` embeds ``world_digest``
and ``World.digest()`` hashes ``full.sigma.tobytes()`` -- BLAS sums in a
CPU-dependent order, so two engineers on different hardware exporting the same
case got different topics. This is the one defect of that kind a superintendent
could see without opening hex.

So a topic GUID rests on ``portable_world_digest`` whenever the caller can supply
one, via a ``cse-world-identity-v1`` record from the run that produced the
disposition. When it cannot, the GUID falls back to ``case_digest`` and both the
topic label and its body say ``identity: machine-local``, because a GUID that
only looks portable is worse than one that admits it is not.

The portable key deliberately drops every float-derived answer -- ``confidence``,
``verdict``, ``p_satisfies_*`` -- and keeps the question: the portable digest, the
case, the subject, the policy, and each check's ``(check_id, kind)``. A verdict is
a float comparison, so near a threshold it is exactly what does not survive a
change of processor, and putting it in the key would reintroduce the defect this
removes. Two consequences, both stated in the topic body rather than left for a
reader to discover: a topic keeps its GUID across re-exports while its
``TopicStatus`` moves, which is what tracking a topic in Solibri needs; and two
beliefs differing only in the 13th significant digit share a portable digest and
therefore share a topic.

*Claim scope.* A BCF topic is a request, never an authorization. Every topic
carries the disposition, ``may_authorize``, the world digest it was computed on
and the claim scope, so a topic cannot be mistaken for a stamp once it leaves
the runtime. ``ApprovalRecord`` is still human.

Consumes the document ``AcceptanceOutcome.to_dict()`` produces, so it also runs
against a pinned disposition in ``validation/`` without a live session.

stdlib only: zipfile and xml.etree.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

BCF_VERSION = "2.1"
BCF_SCHEMA = "cse-bcf-export-v1"

#: Fixed namespace so a topic GUID is a function of the disposition, not of when
#: it was exported. uuid5 over (key, check_id) inside this namespace, where the
#: key is a portable topic key when one can be computed and ``case_digest``
#: otherwise.
TOPIC_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://notation.systems/cse/bcf")

#: The identity a topic GUID rests on, carried as a label and in the body so it
#: travels with the file rather than living only here.
IDENTITY_PORTABLE = "portable"
IDENTITY_MACHINE_LOCAL = "machine-local"

#: Named so a key can be recognised, and versioned so changing what goes into it
#: is a visible schema change rather than a silent renumbering of every topic.
TOPIC_KEY_SCHEMA = "cse-bcf-topic-key-v1"

#: The identity record ``gat.adapters.portable_identity.world_identity`` emits.
#: Mirrored as a string, not imported, so this module still runs on a document
#: and an identity file with no live session.
IDENTITY_SCHEMA = "cse-world-identity-v1"

#: A disposition is a recommendation. BCF has no field for that, so it is said
#: in every topic body instead of being dropped on export.
NOT_AN_APPROVAL = (
    "This topic is a request for evidence, not an approval. "
    "CSE may_authorize is false; authorization is a human ApprovalRecord."
)

_STATUS = {
    "REQUEST_EVIDENCE": "Open",
    "REJECT": "Open",
    "ACCEPT": "Closed",
}
_PRIORITY = {
    "REQUEST_EVIDENCE": "Normal",
    "REJECT": "High",
    "ACCEPT": "Low",
}


class BcfExportError(ValueError):
    """The disposition cannot be expressed as BCF without inventing something."""


def topic_guid(key: str, check_id: str) -> str:
    """Deterministic topic GUID. Same key in, same GUID out.

    ``key`` is whatever identifies the case: a portable topic key from
    :func:`portable_topic_key`, or ``case_digest`` when no identity record is
    available. The function does not know which, on purpose -- the caller decides
    and :func:`topic_identity` records the decision.
    """
    return str(uuid.uuid5(TOPIC_NAMESPACE, f"{key}/{check_id}"))


def _hex64(value: object, what: str) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise BcfExportError(
            f"{what} must be a 64-character lowercase sha256; got {value!r}. "
            "A prefix is not a digest: a topic GUID derived from one would look "
            "as authoritative as any other and identify a different thing."
        )
    return text


def portable_topic_key(
    document: Mapping[str, object], portable_digest: str
) -> str:
    """The case, identified without the processor it ran on.

    Everything in the key is either a string from the model or the portable
    digest. Every float-derived field is excluded -- see the module docstring for
    why a verdict cannot be in a key that is meant to survive a change of CPU.
    """
    payload = {
        "schema": TOPIC_KEY_SCHEMA,
        "portable_digest": _hex64(portable_digest, "portable_digest"),
        "case_id": str(_require(document, "case_id")),
        "workflow": str(document.get("workflow") or ""),
        "subject": str(document.get("subject") or ""),
        "policy_id": str(document.get("policy_id") or ""),
        "checks": sorted(
            (
                {
                    "check_id": str(check.get("check_id")),
                    "kind": str(check.get("kind")),
                }
                for check in document.get("checks") or ()
                if isinstance(check, Mapping)
            ),
            key=lambda entry: entry["check_id"],
        ),
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def topic_identity(
    document: Mapping[str, object],
    world_identity: Mapping[str, object] | None,
) -> tuple[str, str]:
    """The key a topic GUID rests on, and which kind of identity that is.

    An identity record for a *different* world cannot be used to make this
    disposition's topics look portable, so the record's ``world_digest`` must
    match the document's. That check is the whole value of passing the record
    rather than a bare digest: without it, handing over any identity file would
    relabel these topics portable while the number came from another run.
    """
    if world_identity is None:
        return str(_require(document, "case_digest")), IDENTITY_MACHINE_LOCAL

    if not isinstance(world_identity, Mapping):
        raise BcfExportError("world_identity must be a JSON object or None")

    schema = world_identity.get("schema")
    if schema != IDENTITY_SCHEMA:
        raise BcfExportError(
            f"world identity must be {IDENTITY_SCHEMA}, got {schema!r}"
        )

    declared = world_identity.get("world_digest")
    on_the_case = document.get("world_digest")
    if declared != on_the_case:
        raise BcfExportError(
            "world identity is for a different world: it declares world_digest "
            f"{declared!r} and the disposition was computed on {on_the_case!r}. "
            "A portable digest from another run does not make these topics "
            "portable; it makes them wrong."
        )

    portable = world_identity.get("portable_digest")
    if portable is None:
        raise BcfExportError(
            "world identity carries no portable_digest, so it cannot make a "
            "topic GUID portable. Omit the record to export machine-local "
            "GUIDs, which at least say so."
        )
    return portable_topic_key(document, str(portable)), IDENTITY_PORTABLE


def _require(document: Mapping[str, object], key: str) -> object:
    if key not in document:
        raise BcfExportError(f"disposition document has no {key!r}")
    return document[key]


def _check_by_id(document: Mapping[str, object], check_id: str) -> Mapping[str, object]:
    for check in document.get("checks") or ():
        if isinstance(check, Mapping) and check.get("check_id") == check_id:
            return check
    return {}


def _describe(
    document: Mapping[str, object],
    request: Mapping[str, object],
    world_identity: Mapping[str, object] | None,
    identity_kind: str = IDENTITY_MACHINE_LOCAL,
) -> str:
    check = _check_by_id(document, str(request.get("check_id")))
    lines = [
        str(request.get("reason") or "evidence required"),
        "",
        f"case: {document.get('case_id')}  ({document.get('workflow')})",
        f"subject: {document.get('subject')}",
        f"disposition: {document.get('disposition')}  policy: {document.get('policy_id')}",
        f"may_authorize: {document.get('may_authorize')}",
    ]
    if check:
        lines += [
            "",
            f"check {check.get('check_id')}: {check.get('kind')} -> {check.get('verdict')}",
            f"confidence: {check.get('confidence')}",
        ]
        details = check.get("details")
        if isinstance(details, Mapping):
            for key in sorted(details):
                lines.append(f"  {key}: {details[key]}")
    lines += [
        "",
        f"world_digest: {document.get('world_digest')}",
        f"case_digest: {document.get('case_digest')}",
    ]
    if world_identity:
        lines.append(f"portable_digest: {world_identity.get('portable_digest')}")
        lines.append(f"source: {world_identity.get('source')}")
    lines += ["", f"topic GUID identity: {identity_kind}"]
    if identity_kind == IDENTITY_PORTABLE:
        lines += [
            "  This GUID is derived from portable_world_digest, so the same case "
            "exported on another processor is the same topic.",
            "  It is derived from the case, the subject, the policy and each "
            "check's kind -- not from any verdict or confidence. So this topic "
            "keeps its GUID across re-exports while its TopicStatus moves, and "
            "two beliefs differing only in the 13th significant digit share it.",
        ]
    else:
        lines += [
            "  This GUID is derived from case_digest, which embeds world_digest "
            "and is therefore specific to the processor this ran on. The same "
            "case exported elsewhere may be a DIFFERENT topic. Export with a "
            "cse-world-identity-v1 record to get a portable GUID.",
        ]
    lines += ["", NOT_AN_APPROVAL]
    return "\n".join(lines)


def bcf_topics(
    document: Mapping[str, object],
    *,
    created: str,
    author: str,
    world_identity: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """One topic per evidence request, in deterministic check-id order.

    ``created`` is an ISO-8601 timestamp supplied by the caller; this module
    never reads a clock, so the same disposition and the same timestamp always
    produce the same topics.
    """
    if not created or not author:
        raise BcfExportError("BCF requires a creation date and author; supply both")
    disposition = str(_require(document, "disposition"))
    key, identity_kind = topic_identity(document, world_identity)
    requests = document.get("evidence_requests") or ()

    topics: list[dict[str, object]] = []
    for request in sorted(
        (r for r in requests if isinstance(r, Mapping)),
        key=lambda r: str(r.get("check_id")),
    ):
        check_id = str(request.get("check_id"))
        topics.append(
            {
                "guid": topic_guid(key, check_id),
                "identity": identity_kind,
                "title": f"{request.get('target')}: {request.get('action')}",
                "status": _STATUS.get(disposition, "Open"),
                "priority": _PRIORITY.get(disposition, "Normal"),
                "created": created,
                "author": author,
                "labels": [
                    str(document.get("workflow") or "ACCEPTANCE"),
                    disposition,
                    "claim_scope:record-integrity-only",
                    f"identity:{identity_kind}",
                ],
                "description": _describe(
                    document, request, world_identity, identity_kind
                ),
            }
        )
    return topics


#: BCF 2.1 declares Topic's children as an ordered xs:sequence. Emitting them
#: out of order still parses in lenient readers and is rejected by a validating
#: one, so the order here is the schema's, not a convenient one:
#: Title, Priority, Index, Labels*, CreationDate, CreationAuthor, ..., Description.
_XSI = "http://www.w3.org/2001/XMLSchema-instance"


def _markup(topic: Mapping[str, object]) -> bytes:
    markup = ET.Element("Markup", {"xmlns:xsi": _XSI})
    node = ET.SubElement(
        markup,
        "Topic",
        {"Guid": str(topic["guid"]), "TopicType": "Issue", "TopicStatus": str(topic["status"])},
    )
    ET.SubElement(node, "Title").text = str(topic["title"])
    ET.SubElement(node, "Priority").text = str(topic["priority"])
    for label in topic.get("labels") or ():
        ET.SubElement(node, "Labels").text = str(label)
    ET.SubElement(node, "CreationDate").text = str(topic["created"])
    ET.SubElement(node, "CreationAuthor").text = str(topic["author"])
    ET.SubElement(node, "Description").text = str(topic["description"])
    comment = ET.SubElement(markup, "Comment", {"Guid": topic_guid(str(topic["guid"]), "comment")})
    ET.SubElement(comment, "Date").text = str(topic["created"])
    ET.SubElement(comment, "Author").text = str(topic["author"])
    ET.SubElement(comment, "Comment").text = NOT_AN_APPROVAL
    return _xml_bytes(markup)


def _version_bytes() -> bytes:
    version = ET.Element("Version", {"xmlns:xsi": _XSI, "VersionId": BCF_VERSION})
    ET.SubElement(version, "DetailedVersion").text = BCF_VERSION
    return _xml_bytes(version)


def _xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def write_bcfzip(
    path: str | Path,
    document: Mapping[str, object],
    *,
    created: str,
    author: str,
    world_identity: Mapping[str, object] | None = None,
) -> list[str]:
    """Write a .bcfzip and return the topic GUIDs it contains.

    Entries are written with a fixed timestamp and in sorted order, so the same
    disposition exports to identical bytes -- a BCF file can be digested and
    replayed like anything else in this runtime.
    """
    topics = bcf_topics(
        document, created=created, author=author, world_identity=world_identity
    )
    if not topics:
        raise BcfExportError(
            f"disposition {document.get('disposition')!r} raises no evidence "
            "request, so there is nothing for a reviewer to act on"
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        _write(archive, "bcf.version", _version_bytes())
        for topic in topics:
            _write(archive, f"{topic['guid']}/markup.bcf", _markup(topic))
    return [str(topic["guid"]) for topic in topics]


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    # Fixed date_time: a zip's mtime is not part of the claim, and letting it
    # float would make two exports of one disposition differ.
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def read_topic_guids(path: str | Path) -> Sequence[str]:
    """Topic GUIDs in a .bcfzip, for checking a round trip."""
    with zipfile.ZipFile(Path(path)) as archive:
        return tuple(
            sorted(
                name.split("/", 1)[0]
                for name in archive.namelist()
                if name.endswith("/markup.bcf")
            )
        )
