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

So this module adds a second identity rather than changing the first. The
portable digest is computed the same way, over the same bytes, with ``source``
normalized out. Nothing here moves ``World.digest()`` or any value pinned
against it.

**What "portable" does and does not mean here.** This docstring used to open by
claiming an identity that "survives leaving the machine it was computed on",
and that was wrong. Both digests end in ``full.sigma.tobytes()`` -- the raw
float64 bytes of a covariance built by BLAS -- and BLAS sums in an order that
depends on the CPU it finds. The table above is a fact about this processor:
the same code on a Haswell-class core gives ``6df20d41...`` for the first row.
Eliding ``source`` fixes path spelling and nothing else. See
``docs/digest-portability-v1.md`` for the measurements.

    world_digest      this lowering, here, named this way, on this CPU
    portable_digest   this model and this belief, in any checkout, on this CPU

Use ``world_digest`` to check that a decision and a model are the same
lowering. Use ``portable_digest`` when the claim has to cross a repository or a
checkout. Neither crosses a processor, and until the covariance is compared to
a declared tolerance instead of by byte equality, neither can.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

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


def portable_world_digest(world: World) -> str:
    """``World.digest()`` computed over a location-free module digest.

    Mirrors the kernel's own composition -- module digest, then the full-view
    mean and covariance -- so the belief still participates. Two worlds with
    equal portable digests are the same model carrying the same belief.
    """
    digest = hashlib.sha256()
    digest.update(portable_module_digest(world.module).encode("utf-8"))
    digest.update(world.full.mu.tobytes())
    digest.update(world.full.sigma.tobytes())
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
        "source": world.module.meta.get("source"),
        "location_meta_elided": list(LOCATION_META_KEYS),
        "rule": (
            "world_digest is this lowering named this way; portable_digest is "
            "this model and belief anywhere. cite the portable one across repos."
        ),
    }


def same_world(left: World, right: World) -> bool:
    """True when two worlds are the same model and belief, however named."""
    return portable_world_digest(left) == portable_world_digest(right)
