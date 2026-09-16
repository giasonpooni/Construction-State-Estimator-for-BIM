"""Tests for the external PLY scan-artifact boundary.

The loader supports both common standard PLY encodings and only admits
unambiguous x/y/z vertex data.  A final integration test loads the binary
3DGS PLY emitted by GAT itself, proving that the same adapter can consume
standard external Gaussian-splat mesh/point artifacts without a producer
runtime dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

import gat.demo
from gat.errors import ScanArtifactError
from gat.geometry.registration import (
    RigidTransformZ,
    ScanRegistrar,
    _scan_digest,
    synthesize_scan,
)
from gat.geometry.scan_io import load_ply_points, read_ply_scan
from gat.geometry.splat_io import export_splat_ply
from gat.geometry.stateio import derive_scene
from gat.session import GatSession


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


class PlyScanIoTests(unittest.TestCase):
    def test_loads_ascii_vertices_in_declared_property_order(self) -> None:
        source = (
            "ply\n"
            "format ascii 1.0\n"
            "comment mesh faces follow vertices and are ignored\n"
            "element vertex 2\n"
            "property float z\n"
            "property uchar red\n"
            "property double x\n"
            "property float y\n"
            "element face 1\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
            "3.0 255 1.5 -2.0\n"
            "6.0 10 -4.0 8.5\n"
            "3 0 1 0\n"
        ).encode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mesh_ascii.ply"
            path.write_bytes(source)
            points = load_ply_points(path)

        np.testing.assert_allclose(points, [[1.5, -2.0, 3.0], [-4.0, 8.5, 6.0]])
        self.assertFalse(points.flags.writeable)

    def test_loads_binary_little_endian_vertices(self) -> None:
        header = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            "element vertex 2\n"
            "property float y\n"
            "property double x\n"
            "property uchar confidence\n"
            "property float z\n"
            "end_header\n"
        ).encode("ascii")
        body = struct.pack("<fdBf", -2.0, 1.5, 255, 3.0) + struct.pack(
            "<fdBf", 8.5, -4.0, 10, 6.0
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mesh_binary.ply"
            path.write_bytes(header + body)
            points = load_ply_points(path)

        np.testing.assert_allclose(points, [[1.5, -2.0, 3.0], [-4.0, 8.5, 6.0]])

    def test_rejects_missing_coordinate_property(self) -> None:
        source = (
            "ply\nformat ascii 1.0\nelement vertex 1\n"
            "property float x\nproperty float y\nend_header\n0 0\n"
        ).encode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.ply"
            path.write_bytes(source)
            with self.assertRaises(ScanArtifactError):
                load_ply_points(path)

    def test_reads_gat_standard_binary_splat_artifact(self) -> None:
        # GAT's 3DGS exporter has x/y/z plus fourteen non-coordinate scalar
        # vertex fields.  A scan adapter must ignore those fields without
        # depending on the original splat exporter or viewer.
        scene = derive_scene(GatSession.load_ifc(MODEL).world)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "building_splats.ply"
            export_splat_ply(scene.cloud, str(path))
            points = load_ply_points(path)

        self.assertEqual(points.shape, scene.cloud.means.shape)
        np.testing.assert_allclose(points, scene.cloud.means, rtol=0.0, atol=1e-6)


class HostileArtifactTests(unittest.TestCase):
    """The declared vertex count is third-party input, not a promise.

    scan_io's contract is to fail loudly rather than partially misread. It
    allocated on the header count directly, so a corrupt or hostile artifact
    raised MemoryError -- an error this module says it does not raise.
    """

    def _write(self, blob: bytes) -> str:
        handle = tempfile.NamedTemporaryFile(suffix=".ply", delete=False)
        handle.write(blob)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    HEADER = (
        b"ply\nformat %s 1.0\nelement vertex %d\n"
        b"property float x\nproperty float y\nproperty float z\nend_header\n"
    )

    def test_an_impossible_binary_count_is_refused_not_allocated(self) -> None:
        path = self._write(self.HEADER % (b"binary_little_endian", 999999999999))
        with self.assertRaises(ScanArtifactError) as caught:
            load_ply_points(path)
        self.assertIn("bytes remain", str(caught.exception))

    def test_an_impossible_ascii_count_is_refused(self) -> None:
        path = self._write(self.HEADER % (b"ascii", 999999999999) + b"0 0 0\n")
        with self.assertRaises(ScanArtifactError):
            load_ply_points(path)

    def test_a_truncated_artifact_is_refused(self) -> None:
        body = np.array([[0, 0, 0], [1, 1, 1]], dtype="<f4").tobytes()
        path = self._write((self.HEADER % (b"binary_little_endian", 100)) + body)
        with self.assertRaises(ScanArtifactError):
            load_ply_points(path)

    def test_a_valid_artifact_still_loads(self) -> None:
        points = np.array([[0, 0, 0], [1, 2, 3], [4, 5, 6]], dtype="<f4")
        path = self._write(
            (self.HEADER % (b"binary_little_endian", 3)) + points.tobytes()
        )
        np.testing.assert_allclose(load_ply_points(path), points.astype(np.float64))


class TrailingNewlineTests(unittest.TestCase):
    """The declared-count ceiling must not charge for a separator that a
    valid file is allowed to omit."""

    HEADER = (
        "ply\nformat ascii 1.0\nelement vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\nend_header\n"
    )

    def _write(self, body: str) -> str:
        path = os.path.join(self.tmp.name, f"cloud{abs(hash(body))}.ply")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_a_file_without_a_final_newline_still_loads(self) -> None:
        path = self._write(self.HEADER.format(n=3) + "0 0 0\n1 1 1\n2 2 2")
        self.assertEqual(len(load_ply_points(path)), 3)

    def test_a_single_vertex_without_a_final_newline_loads(self) -> None:
        self.assertEqual(
            len(load_ply_points(self._write(self.HEADER.format(n=1) + "0 0 0"))), 1
        )

    def test_an_overstated_count_is_still_refused(self) -> None:
        for declared in (4, 99):
            with self.subTest(declared=declared):
                path = self._write(
                    self.HEADER.format(n=declared) + "0 0 0\n1 1 1\n2 2 2"
                )
                with self.assertRaisesRegex(ScanArtifactError, "can hold at most"):
                    load_ply_points(path)

class ScanArtifactBindsTheFileTests(unittest.TestCase):
    """``scan_digest`` covers the parsed coordinates; nothing covered the file.

    ``RegistrationResult.scan_digest`` was commented "binds downstream
    evidence to exact input bytes". It does not: ``_scan_digest``
    (gat/geometry/registration.py) hashes the parsed ``float64`` positions.
    Everything a PLY says *about* those positions -- a provenance comment,
    per-splat scales, opacity -- is outside it, and so is outside the ledger
    event hash and the proof statement built on top.

    Measured: four byte-distinct files carrying identical vertex positions
    produced one scan digest. Two of them make opposite claims about what was
    measured -- 1 m isotropic splats at opacity 0.02 against 2 mm splats at
    opacity 0.99 -- and were indistinguishable downstream.

    The certificate path had this right all along:
    ``material_certificate`` hashes ``source_bytes`` and
    ``certificate_signature`` HMACs them. The scan path had no equivalent, so
    a point cloud was trusted on arrival. ``ScanArtifact`` does not make it
    trusted -- nothing here verifies a signature -- it makes it
    identifiable, which is the precondition for ever signing one.
    """

    def _write(self, path, points, *, comments=(), props=(), values=None):
        n = len(points)
        head = ["ply", "format binary_little_endian 1.0"]
        head += [f"comment {c}" for c in comments]
        head += [f"element vertex {n}"]
        head += [f"property double {a}" for a in ("x", "y", "z")]
        head += [f"property float {q}" for q in props]
        head += ["end_header", ""]
        with open(path, "wb") as handle:
            handle.write("\n".join(head).encode("ascii"))
            for index, point in enumerate(points):
                handle.write(struct.pack("<3d", *point))
                if props:
                    handle.write(struct.pack(f"<{len(props)}f", *values[index]))

    def _variants(self, directory, points):
        """Four files, identical vertex positions, different claims."""
        plain = os.path.join(directory, "plain.ply")
        self._write(plain, points)

        forged = os.path.join(directory, "forged.ply")
        self._write(
            forged,
            points,
            comments=[
                "captured by Leica RTC360 s/n 4417281",
                "survey control CAL-UTM-2026-08",
            ],
        )

        splat_props = ("scale_0", "scale_1", "scale_2", "opacity")
        blobs = os.path.join(directory, "blobs.ply")
        self._write(
            blobs,
            points,
            props=splat_props,
            values=np.hstack(
                [
                    np.full((len(points), 3), 1.0, dtype=np.float32),
                    np.full((len(points), 1), 0.02, dtype=np.float32),
                ]
            ),
        )

        tight = os.path.join(directory, "tight.ply")
        self._write(
            tight,
            points,
            props=splat_props,
            values=np.hstack(
                [
                    np.full((len(points), 3), 0.002, dtype=np.float32),
                    np.full((len(points), 1), 0.99, dtype=np.float32),
                ]
            ),
        )
        return {"plain": plain, "forged": forged, "blobs": blobs, "tight": tight}

    def test_the_artifact_digest_separates_what_the_coordinates_do_not(
        self,
    ) -> None:
        rng = np.random.default_rng(1)
        points = rng.uniform(-1.0, 1.0, size=(200, 3))
        with tempfile.TemporaryDirectory() as directory:
            variants = self._variants(directory, points)
            coordinate_digests = set()
            artifact_digests = set()
            for path in variants.values():
                artifact = read_ply_scan(path)
                np.testing.assert_allclose(artifact.points, points)
                coordinate_digests.add(_scan_digest(artifact.points))
                artifact_digests.add(artifact.source_digest)

            # The coordinates really are identical -- that is the premise.
            self.assertEqual(len(coordinate_digests), 1)
            # And the artifact digest tells the four files apart.
            self.assertEqual(len(artifact_digests), len(variants))

    def test_the_two_reconstructions_that_contradict_each_other_differ(
        self,
    ) -> None:
        """1 m isotropic blobs at 2% opacity and 2 mm splats at 99% opacity
        are opposite claims about what was measured. Before, one digest."""
        rng = np.random.default_rng(2)
        points = rng.uniform(-1.0, 1.0, size=(200, 3))
        with tempfile.TemporaryDirectory() as directory:
            variants = self._variants(directory, points)
            blobs = read_ply_scan(variants["blobs"])
            tight = read_ply_scan(variants["tight"])
            self.assertEqual(blobs.source_bytes, tight.source_bytes)
            self.assertEqual(_scan_digest(blobs.points), _scan_digest(tight.points))
            self.assertNotEqual(blobs.source_digest, tight.source_digest)

    def test_the_artifact_records_a_basename_not_a_path(self) -> None:
        """World identity is path-independent by design
        (docs/world-identity-v2.md); evidence must not smuggle the
        exporter's directory layout back in."""
        rng = np.random.default_rng(3)
        points = rng.uniform(-1.0, 1.0, size=(50, 3))
        with tempfile.TemporaryDirectory() as directory:
            nested = os.path.join(directory, "clientname_x")
            os.makedirs(nested)
            path = os.path.join(nested, "survey.ply")
            self._write(path, points)
            artifact = read_ply_scan(path)
            self.assertEqual(artifact.source_name, "survey.ply")
            self.assertNotIn("clientname_x", artifact.source_name)
            self.assertGreater(artifact.source_bytes, 0)

    def test_registering_a_file_carries_the_byte_identity_through(self) -> None:
        scene = derive_scene(GatSession.load_ifc(MODEL).world)
        registrar = ScanRegistrar(scene)
        truth = RigidTransformZ(0.0, (0.0, 0.0, 0.0))
        scan = synthesize_scan(
            scene, n_points=600, noise_sigma=0.01, outlier_frac=0.02,
            transform=truth, seed=5,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "scan.ply")
            self._write(path, scan)
            artifact = read_ply_scan(path)
            result = registrar.register_ply(path)
            self.assertEqual(result.artifact_digest, artifact.source_digest)
            self.assertEqual(result.scan_digest, _scan_digest(artifact.points))
            self.assertNotEqual(result.artifact_digest, result.scan_digest)

    def test_an_in_memory_scan_claims_no_byte_provenance(self) -> None:
        """Optional on purpose. A scan with no file behind it must not
        assert one, and every digest recorded before this existed must be
        unchanged."""
        scene = derive_scene(GatSession.load_ifc(MODEL).world)
        registrar = ScanRegistrar(scene)
        scan = synthesize_scan(
            scene, n_points=600, noise_sigma=0.01, outlier_frac=0.02,
            transform=RigidTransformZ(0.0, (0.0, 0.0, 0.0)), seed=5,
        )
        self.assertIsNone(registrar.register(scan).artifact_digest)

    def test_a_missing_artifact_is_a_declared_refusal(self) -> None:
        with self.assertRaises(ScanArtifactError):
            read_ply_scan("/nonexistent/none.ply")



if __name__ == "__main__":
    unittest.main()
