"""Where a declared artifact lives, and what to say when it does not.

``validation/`` is a repository directory, not package data. ``pip install .``
builds a wheel with no ``validation/`` in it at all, so a loader that resolves
the repo root from ``__file__`` works in the editable install CI uses and raises
``FileNotFoundError`` on a real one. Refusing is right -- an installed runtime
that cannot read its declared identity corpus must not needle anything -- but
the error named a path on the machine that built the wheel, which tells the
reader nothing about what to do.

So the refusal stays and gets a reason, plus the override this repository
already uses elsewhere for exactly this: an environment variable naming the
validation root, like ``GAT_IFC_VALIDATION_ROOT`` does for the public corpus.

``ArtifactMissing`` subclasses ``FileNotFoundError`` so every existing caller
and the CLI's own handling keep working unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Point this at a checkout's ``validation/`` directory when running from an
#: installed wheel rather than a source tree.
ENV_ROOT = "GAT_VALIDATION_ROOT"

#: The source-tree location, correct for an editable install.
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "validation"


class ArtifactMissing(FileNotFoundError):
    """A declared validation artifact is not reachable from this install."""


def validation_root() -> Path:
    """The validation directory: the environment override, else the source tree."""
    override = os.environ.get(ENV_ROOT)
    return Path(override).expanduser() if override else SOURCE_ROOT


def validation_artifact(name: str) -> Path:
    """Resolve one artifact by file name, or refuse with something actionable."""
    root = validation_root()
    candidate = root / name
    if candidate.is_file():
        return candidate
    source = "the " + ENV_ROOT + " override" if os.environ.get(ENV_ROOT) else "the source tree"
    raise ArtifactMissing(
        f"{name} is not under {root} ({source}). validation/ is a repository "
        f"directory and is not packaged, so an installed wheel has no copy: set "
        f"{ENV_ROOT} to a checkout's validation/ directory, or pass an explicit "
        f"path. Refusing rather than continuing without the declared artifact."
    )
