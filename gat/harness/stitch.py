"""Compose instrument artifacts only where the axioms survive the join.

Three instruments, three typed objects, and the whole content of this module is
the refusal at each arrow:

    declare plant / IFC world
      -> JSPT      A = J(x*)          square, finite, within the certificate law
      -> PLSR      verdict on A        bound to that exact A, from the real vocabulary
      -> CSE       disposition         a certificate is support, never authorization

A script is legal only when the codomain of the previous object is the domain of
the next. A non-square beam Jacobian does not become an ``A``. A verdict on one
matrix does not transfer to another. A certificate does not become ACCEPT. Those
are checked *before* anything runs, and a miss is a refusal with a reason, not an
exception swallowed into the next stage.

What this module deliberately is not:

- It imports no companion runtime. The portfolio rule is "each repo keeps local
  I. none import another runtime", so this reads JSON and checks laws. The
  companion's own constants are mirrored here and a test asserts they agree
  wherever the companion is importable -- the same agreement-not-import pattern
  used for the JSPT ownership pin.
- It computes nothing. No Jacobian, no Lyapunov solve, no device. The linear bulk
  belongs inside one kernel with an oracle match test; a stitcher that also
  computed would be the megascript this is meant to avoid.
- It invents no verdicts. PLSR's shipped vocabulary is VERIFIED / INVALID /
  NOT_CHECKED. Codes that have been discussed but not shipped are not accepted
  here, because an axiom system whose terms exist only in prose refuses nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from gat.adapters.external_commitment import canonical_digest
from gat.errors import GatError

STITCH_SCHEMA = "cse-stitch-v1"
PLANT_SCHEMA = "cse-plant-a-v1"
RECEIPT_SCHEMA = "plsr-receipt-v1"

#: Mirrored from the companion's frozen numeric law (lyapunov.constitution).
#: Not imported: asserted equal by tests/test_stitch.py wherever the companion
#: is importable.
#:
#: A bare mirrored constant is only safe while someone can see it drifted, and in
#: a deployment the companion is not checked out, so the agreement test cannot
#: run. Every stitch record therefore reports the law it applied together with
#: the commit these values were last read at, so a downstream reader can detect
#: skew without having the companion at all.
#:
#: MIRRORED_AT is a verification pin, not an origin claim: it names the commit
#: whose lyapunov.constitution was read and found equal to the values below. It
#: does not claim that commit first fixed the law -- reading a shallow clone
#: cannot establish that, and a pin that overstates what was checked is the
#: failure this field exists to prevent.
MAX_KRONECKER_DIM = 24
SYMMETRY_ATOL = 1e-12
MIRRORED_SOURCE = "giasonpooni/Parameterized-Lyapunov-Stability-Runtime"
MIRRORED_MODULE = "lyapunov.constitution"
MIRRORED_AT = "d98739e05e0d1bf38c86795ec5ae1a10b7a681c8"
MIRRORED_FROM = f"{MIRRORED_SOURCE}@{MIRRORED_AT[:8]}"

#: The companion's certificate verdicts, from lyapunov.runtime.verdict. Lower
#: case, and these exact four. LYAPUNOV_SAMPLE and SUFFICIENT_COMMON_QUADRATIC
#: have been discussed and are not shipped, so they are refused: a vocabulary
#: that exists only in prose cannot refuse anything.
CERTIFICATE_VERDICTS = frozenset(
    {"certified", "violated", "outside-level", "inconclusive"}
)

#: A DIFFERENT vocabulary: lyapunov.host_callback.ProofStatus, which says whether
#: a bound host verified an SP1 proof. Upper case, and not a stability claim.
#: Keeping these apart is the point -- a verified proof attachment says the
#: arithmetic was checked, not that the plant decreases.
PROOF_STATUSES = frozenset({"NOT_CHECKED", "INVALID", "VERIFIED"})

#: Only a certified sample supports anything, and support is not authorization.
SUPPORTING_VERDICTS = frozenset({"certified"})

TIME_DOMAINS = frozenset({"continuous", "discrete"})


class StitchError(GatError):
    """A join does not type. The sequence stops here."""


@dataclass(frozen=True)
class Plant:
    """``A`` as an artifact: a square matrix with a declared time domain."""

    name: str
    time: str
    matrix: tuple[tuple[float, ...], ...]
    source: str

    @property
    def dimension(self) -> int:
        return len(self.matrix)

    @property
    def digest(self) -> str:
        """Identity of this exact A, so a verdict cannot drift onto another."""
        return canonical_digest(
            {
                "schema": PLANT_SCHEMA,
                "time": self.time,
                "matrix": [list(row) for row in self.matrix],
            }
        )


@dataclass(frozen=True)
class CertificateReceipt:
    """A certificate verdict bound to one plant digest.

    ``proof_status`` is orthogonal: it describes an SP1 attachment, not the
    Lyapunov inequalities, and may never stand in for ``verdict``.
    """

    plant_digest: str
    verdict: str
    dimension: int
    source: str
    proof_status: str = "NOT_CHECKED"
    global_claim: bool = False
    vertex_set: int = 0
    notes: str = ""

    @property
    def supports(self) -> bool:
        return self.verdict in SUPPORTING_VERDICTS


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StitchError(f"{label} must be a JSON object")
    return value


def _text(document: Mapping[str, object], key: str, label: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise StitchError(f"{label} needs non-empty text at {key!r}")
    return value


def read_plant(document: Mapping[str, object]) -> Plant:
    """Read ``A`` and refuse anything that is not a plant.

    Square is the first law: PLSR's ``plant_from_jacobian`` exists to accept
    ``A = J(x*)`` from elsewhere, and a rectangular sensitivity Jacobian -- which
    is what JSPT produces for most models -- is not an ``A``.
    """
    document = _mapping(document, "plant artifact")
    if document.get("schema") != PLANT_SCHEMA:
        raise StitchError(f"plant artifact schema must be {PLANT_SCHEMA}")
    time = _text(document, "time", "plant artifact")
    if time not in TIME_DOMAINS:
        raise StitchError(f"plant time domain must be one of {sorted(TIME_DOMAINS)}")
    rows = document.get("matrix")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise StitchError("plant artifact needs a non-empty matrix")
    matrix: list[tuple[float, ...]] = []
    width = None
    for index, row in enumerate(rows):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
            raise StitchError(f"plant matrix row {index} is not a list")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise StitchError(
                f"plant matrix is ragged: row 0 has {width} entries, row {index} has {len(row)}"
            )
        values = []
        for entry in row:
            if isinstance(entry, bool) or not isinstance(entry, (int, float)):
                raise StitchError(f"plant matrix row {index} has a non-numeric entry")
            number = float(entry)
            if not math.isfinite(number):
                raise StitchError(f"plant matrix row {index} is not finite")
            values.append(number)
        matrix.append(tuple(values))
    height = len(matrix)
    if width != height:
        raise StitchError(
            f"A must be square to be a plant; got {height}x{width}. A rectangular "
            "sensitivity Jacobian is not a plant -- form A = J_f(x*) first."
        )
    if height > MAX_KRONECKER_DIM:
        raise StitchError(
            f"plant dimension {height} exceeds the certificate law's "
            f"MAX_KRONECKER_DIM of {MAX_KRONECKER_DIM}; this is a declared limit, "
            "not a performance budget, so a bigger A is a different axiom set"
        )
    return Plant(
        name=_text(document, "name", "plant artifact"),
        time=time,
        matrix=tuple(matrix),
        source=_text(document, "source", "plant artifact"),
    )


def read_receipt(document: Mapping[str, object]) -> CertificateReceipt:
    """Read a verdict and refuse a vocabulary that does not exist upstream."""
    document = _mapping(document, "certificate receipt")
    if document.get("schema") != RECEIPT_SCHEMA:
        raise StitchError(f"receipt schema must be {RECEIPT_SCHEMA}")
    verdict = _text(document, "verdict", "certificate receipt")
    if verdict in PROOF_STATUSES:
        raise StitchError(
            f"{verdict!r} is a proof status, not a certificate verdict. A verified "
            "proof attachment says the arithmetic was checked; it does not say the "
            f"plant decreases. Report one of {sorted(CERTIFICATE_VERDICTS)}."
        )
    if verdict not in CERTIFICATE_VERDICTS:
        raise StitchError(
            f"{verdict!r} is not a shipped certificate verdict; the companion "
            f"reports one of {sorted(CERTIFICATE_VERDICTS)}"
        )
    dimension = document.get("dimension")
    if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension < 1:
        raise StitchError("certificate receipt needs a positive integer dimension")
    proof_status = str(document.get("proof_status") or "NOT_CHECKED")
    if proof_status not in PROOF_STATUSES:
        raise StitchError(
            f"proof_status {proof_status!r} is not one of {sorted(PROOF_STATUSES)}"
        )
    global_claim = document.get("global_claim", False)
    if not isinstance(global_claim, bool):
        raise StitchError("global_claim must be a boolean")
    vertex_set = document.get("vertex_set", 0)
    if not isinstance(vertex_set, int) or isinstance(vertex_set, bool) or vertex_set < 0:
        raise StitchError("vertex_set must be a non-negative integer")
    if global_claim and vertex_set < 1:
        # The companion is explicit: certified means this sample satisfies the
        # inequalities, and is not a global proof unless the sample set is the
        # declared vertex set of an affine problem.
        raise StitchError(
            "a global stability claim must declare the vertex set it covers; a "
            "certified sample is one point, not a proof over a parameter box"
        )
    return CertificateReceipt(
        plant_digest=_text(document, "plant_digest", "certificate receipt"),
        verdict=verdict,
        dimension=dimension,
        source=_text(document, "source", "certificate receipt"),
        proof_status=proof_status,
        global_claim=global_claim,
        vertex_set=vertex_set,
        notes=str(document.get("notes") or ""),
    )


def check_join(plant: Plant, receipt: CertificateReceipt) -> None:
    """The arrow types, or it does not exist. Checked before any stage runs."""
    if receipt.plant_digest != plant.digest:
        raise StitchError(
            "receipt does not certify this plant: it names "
            f"{receipt.plant_digest[:16]}... and this A digests to "
            f"{plant.digest[:16]}...; a verdict does not transfer between matrices"
        )
    if receipt.dimension != plant.dimension:
        raise StitchError(
            f"receipt is for dimension {receipt.dimension} and this A is "
            f"{plant.dimension}x{plant.dimension}"
        )


def check_cite(document: Mapping[str, object] | None, receipt: CertificateReceipt) -> None:
    """A certificate may support a disposition. It may never authorize one."""
    if document is None:
        return
    document = _mapping(document, "disposition cite")
    if "may_authorize" not in document:
        raise StitchError("disposition cite must state may_authorize")
    if document.get("may_authorize") is not False:
        raise StitchError(
            "a disposition citing a stability certificate must keep "
            "may_authorize false; authorization is a human ApprovalRecord"
        )
    if not receipt.supports and document.get("support_code"):
        raise StitchError(
            f"a {receipt.verdict!r} verdict may not be carried as a support_code; "
            f"only {sorted(SUPPORTING_VERDICTS)} supports anything"
        )


def stitch(
    plant_document: Mapping[str, object],
    receipt_document: Mapping[str, object],
    cite_document: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Type the whole sequence and describe what it does and does not claim."""
    plant = read_plant(plant_document)
    receipt = read_receipt(receipt_document)
    check_join(plant, receipt)
    check_cite(cite_document, receipt)
    return {
        "schema": STITCH_SCHEMA,
        "claim_scope": "record-integrity-only",
        "sequence": [
            {"stage": "plant", "name": plant.name, "source": plant.source,
             "dimension": plant.dimension, "time": plant.time, "digest": plant.digest},
            {"stage": "certificate", "source": receipt.source,
             "verdict": receipt.verdict, "supports": receipt.supports,
             "proof_status": receipt.proof_status,
             "global_claim": receipt.global_claim,
             "vertex_set": receipt.vertex_set},
            {"stage": "disposition",
             "cited": cite_document is not None,
             "may_authorize": False},
        ],
        "law_applied": {
            "max_kronecker_dim": MAX_KRONECKER_DIM,
            "symmetry_atol": SYMMETRY_ATOL,
            "mirrored_from": MIRRORED_FROM,
            "mirrored_module": MIRRORED_MODULE,
            "verified_equal_at": MIRRORED_AT,
            "note": (
                "mirrored, not imported. verified_equal_at names the commit "
                "these values were read at, not the commit that fixed them. "
                "compare against the companion's lyapunov.constitution to "
                "detect skew."
            ),
        },
        "composes": True,
        "not_claimed": [
            "a certified sample is not an ACCEPT",
            "a certified sample is not a global proof unless a vertex set is declared",
            "a proof_status is about arithmetic, not about stability",
            "a certificate on A = J(x*) says nothing about evidence for the world",
            "no device or backend took part in this composition",
        ],
    }


def stitch_files(
    plant_path: str | Path,
    receipt_path: str | Path,
    cite_path: str | Path | None = None,
) -> dict[str, object]:
    """``stitch`` over files. Raises StitchError on a type miss."""
    def _read(path: str | Path) -> Mapping[str, object]:
        text = Path(path).read_text(encoding="utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise StitchError(f"{path} is not valid JSON: {error}") from error

    return stitch(
        _read(plant_path),
        _read(receipt_path),
        _read(cite_path) if cite_path is not None else None,
    )
