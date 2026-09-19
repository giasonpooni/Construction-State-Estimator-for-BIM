"""A world identity that does not depend on how the file was named.

``World.digest()`` hashes the IR printer's output, and the printer emits every
``meta`` key -- including ``source``, which is the path string the caller
happened to pass to ``load_ifc``. So the same file, byte for byte, yields a
different world digest depending only on how its name was spelled. On this
container, with this processor::

    gat/demo/model.ifc                      020383e8...
    ./gat/demo/model.ifc                    e7f0d899...
    /abs/path/to/gat/demo/model.ifc         ae337184...

That is fine for what ``World.digest()`` is: the identity of one lowering, in
one place, which is why the CLI can tell a caller their decision "was
evaluated on a different world than the model". It is not usable as the thing
twelve sibling repos cite. A pinned ``world_digest`` in ``validation/`` is only
reproducible from the exact working directory and the exact path spelling that
produced it, and a citation that cannot be re-derived is a note, not a pin.

So this module adds a second identity rather than changing the first. Nothing
here moves ``World.digest()`` or any value pinned against it.

**Two things make it portable, and it took two passes to get both.** Eliding
``source`` fixes path spelling. It does not fix the other half: ``World.digest()``
ends in ``full.sigma.tobytes()``, the raw float64 bytes of a covariance built by
BLAS, and BLAS sums in a CPU-dependent order. The first version of this module
copied that composition and so inherited the problem, while its docstring claimed
an identity that "survives leaving the machine it was computed on". That claim was
retracted, and is now earned instead: the full view is hashed as canonical decimal
text at ``PORTABLE_SIGNIFICANT_DIGITS``, so a last-bit difference cannot reach the
hash. Measured across five forced OpenBLAS kernels (``SKYLAKEX``, ``HASWELL``,
``ZEN``, ``SANDYBRIDGE``, ``NEHALEM``), on ``gat/demo/model.ifc``:

    World.digest()            4 distinct values
    portable_world_digest()   1

    world_digest      this lowering, here, named this way, on this CPU
    portable_digest   this model and this belief to 12 significant digits,
                      in any checkout, on any processor

Use ``world_digest`` to check that a decision and a model are the same lowering --
that is what its path- and CPU-sensitivity is *for*, and why the CLI can tell a
caller their decision "was evaluated on a different world than the model". Use
``portable_digest`` when the claim has to cross a repository, a checkout, or a
machine.

The trade is explicit and is the point: the portable digest is coarser. Two
beliefs differing in the 13th significant digit share it. For an identity that is
the correct resolution -- they are the same estimate by any engineering standard
-- but it means the portable digest can never be used to claim bitwise restart
identity. ``computational_equivalence`` is the tool for that, and
``docs/digest-portability-v1.md`` has the measurements behind the digit count.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np

from gat.engine.executor import World
from gat.ir.core import Module
from gat.ir.printer import print_module

IDENTITY_SCHEMA = "cse-world-identity-v1"

# Meta keys whose value names where the model was read from rather than what
# the model is. Normalized out of the portable digest.
LOCATION_META_KEYS = ("source",)
_ELIDED = "<elided>"


def portable_meta(meta) -> dict[str, object]:
    """``meta`` with every location-bearing key elided, order preserved."""
    return {
        key: (_ELIDED if key in LOCATION_META_KEYS else value)
        for key, value in meta.items()
    }


def portable_module_digest(module: Module) -> str:
    """SHA-256 of the printer dump with location meta elided."""
    normalized = replace(module, meta=portable_meta(module.meta))
    return hashlib.sha256(print_module(normalized).encode("utf-8")).hexdigest()


#: Significant decimal digits kept from each full-view value before hashing.
#:
#: The reason this exists at all: ``World.digest()`` hashes the covariance as raw
#: float64 bytes, BLAS sums in a CPU-dependent order, and float addition is not
#: associative -- so the same model gives four different digests across five
#: OpenBLAS kernels. A digest that is meant to cross a machine cannot be a hash
#: of raw BLAS output. See docs/digest-portability-v1.md.
#:
#: Why twelve. The worst cross-kernel relative difference measured was 1.920e-16,
#: which is 0.86 eps. Rounding flips when a value sits within its own wobble of a
#: rounding boundary, so the question is the *per-value* margin. Measured over
#: every full-view value of both shipped models:
#:
#:     digits   office worst ratio   beam worst ratio
#:       15           1.31              3.42
#:       14          24.6              34.2
#:       13         261               342
#:       12        2620              3420
#:       10           1.15e+05          3.42e+05
#:        8           2.62e+07          3.42e+07
#:        6           1.85              3.42e+09
#:
#: Twelve keeps a 2620x margin on the model that stresses it, with no value
#: within one perturbation of a flip, and still keeps twelve digits of the
#: covariance -- far more precision than a representation quantum would leave.
#:
#: Note the 6-digit row: a *coarser* grid scored 1.85, worse than 12. Coarser is
#: not monotonically safer, because a coarser grid can place a boundary right
#: beside a value. The margin has to be measured, not reasoned about.
PORTABLE_SIGNIFICANT_DIGITS = 12


def _canonical_number(value: float) -> str:
    """One full-view value as canonical decimal text.

    Decimal formatting rather than arithmetic rounding, for three reasons:
    CPython's float formatting is correctly rounded and platform-independent, it
    avoids the representation error in ``10.0 ** k``, and it avoids numpy's
    banker's rounding landing differently on a tie. It also keeps this digest the
    same kind of object the kernel's module digest already is -- a hash of
    canonical text rather than of machine words.
    """
    return f"{float(value):.{PORTABLE_SIGNIFICANT_DIGITS - 1}e}"


def portable_world_digest(world: World) -> str:
    """A world identity that survives both a rename and a change of processor.

    Same composition as the kernel's -- module digest, then the full-view mean
    and covariance, so the belief still participates -- with two differences:
    ``source`` is elided from the module, and every float is hashed as canonical
    decimal text at ``PORTABLE_SIGNIFICANT_DIGITS`` rather than as raw bytes.

    Two worlds with equal portable digests are the same model carrying the same
    belief to twelve significant digits, wherever either was computed.
    """
    digest = hashlib.sha256()
    digest.update(portable_module_digest(world.module).encode("utf-8"))
    digest.update(f"digits={PORTABLE_SIGNIFICANT_DIGITS}".encode("utf-8"))
    for array in (world.full.mu, world.full.sigma):
        digest.update(b"|")
        for value in np.asarray(array, dtype=float).ravel(order="C"):
            digest.update(_canonical_number(value).encode("utf-8"))
            digest.update(b",")
    return digest.hexdigest()


def world_identity(world: World) -> dict[str, object]:
    """Both identities plus the location that distinguishes them.

    A cross-repo citation should carry this whole record: the portable digest
    is what another repo can check, and ``source`` is kept in the clear so the
    local digest stays explainable rather than mysterious.
    """
    return {
        "schema": IDENTITY_SCHEMA,
        "claim_scope": "record-integrity-only",
        "world_digest": world.digest(),
        "portable_digest": portable_world_digest(world),
        "portable_significant_digits": PORTABLE_SIGNIFICANT_DIGITS,
        "source": world.module.meta.get("source"),
        "location_meta_elided": list(LOCATION_META_KEYS),
        "rule": (
            "world_digest is this lowering named this way, on this CPU; "
            "portable_digest is this model and belief to "
            f"{PORTABLE_SIGNIFICANT_DIGITS} significant digits, anywhere. "
            "cite the portable one across repos or machines."
        ),
    }


def same_world(left: World, right: World) -> bool:
    """True when two worlds are the same model and belief, however named."""
    return portable_world_digest(left) == portable_world_digest(right)
