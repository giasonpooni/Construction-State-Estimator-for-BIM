"""A declared artifact is reachable, or the refusal says what to do.

validation/ is a repository directory, not package data: a wheel contains none
of it, so load_corpus and load_effort_table -- which resolved the repo root from
__file__ -- worked in the editable install CI uses and raised a bare
FileNotFoundError naming the build machine's path on a real one. CI never saw it
because CI only ever runs pip install -e .

Refusing is correct: a runtime that cannot read its declared identity corpus
must not needle anything. What was wrong was the error. These tests pin the
refusal, its guidance, and the override.

stdlib unittest only.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gat.artifact_paths import (
    ENV_ROOT,
    SOURCE_ROOT,
    ArtifactMissing,
    validation_artifact,
    validation_root,
)
from gat.corpus import CORPUS_FILE, CorpusError, load_corpus
from gat.harness.effort import EFFORT_TABLE_FILE, load_effort_table

_ROOT = Path(__file__).resolve().parents[1]


class ValidationRootTests(unittest.TestCase):
    def test_defaults_to_the_source_tree(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_ROOT, None)
            self.assertEqual(validation_root(), SOURCE_ROOT)
            self.assertEqual(SOURCE_ROOT, _ROOT / "validation")

    def test_the_environment_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_ROOT: tmp}):
                self.assertEqual(validation_root(), Path(tmp))

    def test_a_present_artifact_resolves(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_ROOT, None)
            self.assertTrue(validation_artifact(CORPUS_FILE).is_file())
            self.assertTrue(validation_artifact(EFFORT_TABLE_FILE).is_file())

    def test_a_missing_artifact_refuses_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_ROOT: tmp}):
                with self.assertRaises(ArtifactMissing) as caught:
                    validation_artifact(CORPUS_FILE)
        message = str(caught.exception)
        self.assertIn(CORPUS_FILE, message)
        self.assertIn(ENV_ROOT, message)
        self.assertIn("not packaged", message)
        self.assertIn("Refusing", message)

    def test_the_message_says_which_root_it_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_ROOT: tmp}):
                with self.assertRaises(ArtifactMissing) as caught:
                    validation_artifact("nope.json")
                self.assertIn("override", str(caught.exception))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_ROOT, None)
            with self.assertRaises(ArtifactMissing) as caught:
                validation_artifact("nope.json")
            self.assertIn("source tree", str(caught.exception))

    def test_it_stays_a_filenotfounderror(self) -> None:
        # The CLI catches FileNotFoundError and returns 2; that must keep working.
        self.assertTrue(issubclass(ArtifactMissing, FileNotFoundError))


class LoaderTests(unittest.TestCase):
    def test_loaders_work_from_the_source_tree(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_ROOT, None)
            self.assertEqual(load_corpus().schema, "invariant-corpus-v2")
            self.assertEqual(load_effort_table()["format"], "satellite-effort-v1")

    def test_loaders_follow_the_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (CORPUS_FILE, EFFORT_TABLE_FILE):
                (root / name).write_text(
                    (_ROOT / "validation" / name).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            with mock.patch.dict(os.environ, {ENV_ROOT: str(root)}):
                self.assertEqual(load_corpus().path.parent, root)
                self.assertEqual(load_effort_table()["format"], "satellite-effort-v1")

    def test_an_explicit_path_still_overrides_everything(self) -> None:
        explicit = _ROOT / "validation" / CORPUS_FILE
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_ROOT: tmp}):
                self.assertEqual(load_corpus(explicit).path, explicit)

    def test_a_missing_corpus_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_ROOT: tmp}):
                with self.assertRaises(FileNotFoundError):
                    load_corpus()

    def test_a_malformed_override_corpus_is_still_validated(self) -> None:
        # The override is a location, not a licence: schema checks still apply.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / CORPUS_FILE).write_text(
                json.dumps({"schema": "something-else"}), encoding="utf-8"
            )
            with mock.patch.dict(os.environ, {ENV_ROOT: str(root)}):
                with self.assertRaises(CorpusError):
                    load_corpus()


if __name__ == "__main__":
    unittest.main()
