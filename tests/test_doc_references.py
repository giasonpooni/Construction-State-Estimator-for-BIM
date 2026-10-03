"""Every path and line a doc cites must resolve. Checked, not trusted.

Three defects of exactly one shape turned up in one audit: a doc asserting the
suite passed under a kernel seven lines above its own evidence that it did not, a
module docstring naming the proof statuses as the verdict vocabulary it was
written to keep separate, and a docstring claiming portability the code did not
have. Prose drifts from code silently because nothing runs it.

Not everything a doc claims is mechanically checkable. What is: the file it points
at exists, and a `file.py:123` citation is inside that file. Those are the
citations a reader follows to verify the rest, so a broken one costs more than its
size. This test makes them fail at home.

stdlib unittest only.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: `some/path.py`, `some/path.py:123`, or `RCI:some/path.py` inside backticks.
CITATION = re.compile(
    r"`(?:(?P<repo>[A-Z][A-Za-z0-9-]*):)?"
    r"(?P<target>[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|json|md|ifc|yml|yaml|toml))"
    r"(?::(?P<line>\d+))?`"
)

#: Companion repositories a doc may cite into. A citation prefixed with one of
#: these names a file in another repository, which this test cannot open -- so
#: existence is not checked. The prefix must still be a known companion, so a
#: typo fails rather than silently exempting a local path from every check.
#:
#: Added because the seam doc legitimately cites RCI's half of the budget cite.
#: A cross-repo path is neither a path into this tree nor a bare output name, and
#: treating it as the former made a correct citation look broken.
COMPANION_REPOS = frozenset(
    {
        "RCI",       # Retrofitted-Computational-Instrumentation
        "JSPT",      # Jacobian-Sensitivity-Propagation-Testbed
        "PLSR",      # Parameterized-Lyapunov-Stability-Runtime
        "FSRT",      # Fluid-State-Reconstruction-Testbed
        "GFJF",      # Geodesic-Flow-and-Jacobi-Field-Testbed
        "FTMG",      # Flat-Torus-Moduli-and-Geodesic-Explorer
    }
)

#: Directories a bare basename may name, so `verify.py` in a list whose first
#: item is `gat/engine/propagate.py` still resolves for the line check.
SHORTHAND_DIRS = (
    "",
    "gat",
    "gat/demo",
    "gat/engine",
    "gat/adapters",
    "gat/workflows",
    "gat/harness",
    "validation",
    "docs",
    "tests",
)


def _is_path(target: str) -> bool:
    """Whether a citation is a path into the tree or just a name.

    Docs cite two different kinds of thing in the same backticks. A *path* points
    into the repository -- `gat/engine/executor.py` -- and a reader follows it to
    verify a claim, so it must exist. A bare *name* is usually a file a demo
    writes (`beam_ledger.json`, `STATUS.json`, `calibrate-verify-report.json`) or
    an entry inside an archive (`markup.bcf`), and requiring those to exist would
    mean requiring the demos to have been run.

    So existence is enforced for paths only. Bare names are still line-checked
    when they happen to resolve, which is where drift actually shows up.
    """
    return "/" in target


def _resolve(target: str) -> Path | None:
    """The file a citation names, trying the shorthand directories."""
    if _is_path(target):
        candidate = ROOT / target
        return candidate if candidate.is_file() else None
    if target.count(".") > 1:
        # A dotted module name such as gat.adapters.ifc, not a file.
        return None
    for directory in SHORTHAND_DIRS:
        candidate = ROOT / directory / target if directory else ROOT / target
        if candidate.is_file():
            return candidate
    return None


class DocReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs = sorted((ROOT / "docs").glob("*.md"))
        extra = ROOT / "README.md"
        if extra.is_file():
            cls.docs.append(extra)
        cls.citations: list[tuple[Path, str, str | None]] = []
        cls.foreign: list[tuple[Path, str, str]] = []
        for doc in cls.docs:
            body = doc.read_text(encoding="utf-8")
            for match in CITATION.finditer(body):
                repo = match.group("repo")
                target = match.group("target")
                line = match.group("line")
                if repo is not None:
                    cls.foreign.append((doc, repo, target))
                    continue
                cls.citations.append((doc, target, line))

    def test_there_are_citations_to_check(self) -> None:
        # Guard against the regex silently matching nothing, which would make
        # every other test in this class vacuous.
        self.assertGreater(len(self.docs), 10)
        self.assertGreater(len(self.citations), 50)

    def test_a_cross_repo_citation_names_a_known_companion(self) -> None:
        """A foreign path is not checked for existence, so the prefix is checked.

        Otherwise `RCl:gat/does_not_exist.py` -- capital i for lowercase L -- would
        exempt itself from every check in this file.
        """
        unknown = [
            (doc.name, repo, target)
            for doc, repo, target in self.foreign
            if repo not in COMPANION_REPOS
        ]
        self.assertEqual(
            unknown,
            [],
            f"unknown repository prefix; known companions are {sorted(COMPANION_REPOS)}",
        )

    def test_every_cited_path_exists(self) -> None:
        missing = [
            (doc.name, target)
            for doc, target, _ in self.citations
            if _is_path(target) and _resolve(target) is None
        ]
        self.assertEqual(
            missing,
            [],
            "docs cite files that are not in the tree; a citation a reader "
            "cannot follow is worse than no citation",
        )

    def test_every_cited_line_is_inside_its_file(self) -> None:
        out_of_range = []
        for doc, target, line in self.citations:
            if line is None:
                continue
            path = _resolve(target)
            if path is None:
                continue  # covered by the test above
            count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            if int(line) > count:
                out_of_range.append((doc.name, f"{target}:{line}", f"{count} lines"))
        self.assertEqual(
            out_of_range,
            [],
            "docs cite line numbers past the end of the file they name; the code "
            "moved and the prose did not",
        )

    def test_the_load_bearing_line_citations_still_say_what_the_docs_claim(
        self,
    ) -> None:
        """Line numbers drift. These three carry an argument, so pin the content.

        A line citation that still resolves but now points at unrelated code is
        worse than one that points past the end, because it reads as verified.
        """
        expected = {
            ("gat/engine/executor.py", 136): "def digest",
            ("gat/state_snapshot.py", 259): "reconstructed world digest differs from source",
            ("gat/workflows/acceptance.py", 436): "require_verified_evidence_for_accept",
        }
        for (target, line), fragment in expected.items():
            path = ROOT / target
            with self.subTest(citation=f"{target}:{line}"):
                self.assertTrue(path.is_file(), f"{target} is gone")
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(lines), line)
                self.assertIn(
                    fragment,
                    lines[line - 1],
                    f"{target}:{line} no longer contains {fragment!r}; a doc cites "
                    "it for that",
                )


if __name__ == "__main__":
    unittest.main()
