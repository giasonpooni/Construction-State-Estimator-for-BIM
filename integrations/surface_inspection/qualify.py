"""Build and exercise both real instruments outside either source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def call(command: list[str], *, log: Path | None = None, **kwargs):
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=kwargs.pop("timeout", 600),
        **kwargs,
    )
    if log is not None:
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}; see {log}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cse", type=Path, required=True)
    parser.add_argument("--csg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cse, csg, output = args.cse.resolve(), args.csg.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    revisions = {
        key: call(["git", "-C", str(path), "rev-parse", "HEAD"]).strip()
        for key, path in (("cse", cse), ("csg", csg))
    }
    with tempfile.TemporaryDirectory(prefix="notations-inspection-") as directory:
        root = Path(directory)
        wheels = root / "wheels"
        call(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                str(cse),
                str(csg),
                "--wheel-dir",
                str(wheels),
            ],
            log=output / "build.txt",
        )
        distributions = sorted(wheels.glob("*.whl"))
        if len(distributions) != 2:
            raise AssertionError("Require both separately built instrument wheels")
        venv = root / "environment"
        call([sys.executable, "-m", "venv", str(venv)])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        call(
            [
                str(python),
                "-m",
                "pip",
                "install",
                *map(str, distributions),
                "numpy==2.4.3",
                "pytest==9.0.2",
            ],
            log=output / "install.txt",
        )
        work = root / "outside-checkouts"
        tests = work / "tests"
        tests.mkdir(parents=True)
        for source in (
            cse / "tests/test_surface_inspection.py",
            csg / "tests/test_inspection_exchange.py",
        ):
            shutil.copyfile(source, tests / source.name)
        env = {**os.environ, "CSE_REQUIRE_INSPECTION_PROVIDER": "1"}
        env.pop("PYTHONPATH", None)
        location = call(
            [
                str(python),
                "-I",
                "-c",
                "import gat, geodesic_testbed, json; "
                "print(json.dumps([gat.__file__, geodesic_testbed.__file__]))",
            ],
            cwd=work,
            env=env,
        )
        if not all(Path(p).resolve().is_relative_to(venv) for p in json.loads(location)):
            raise AssertionError("An import escaped the installed environment")
        collection = call(
            [str(python), "-I", "-m", "pytest", "--collect-only", "-q", "tests"],
            log=output / "collection.txt",
            cwd=work,
            env=env,
        )
        match = re.search(r"(\d+) tests? collected", collection)
        if match is None or int(match[1]) < 68:
            raise AssertionError("Complete paired test collection was not obtained")
        call(
            [
                str(python),
                "-I",
                "-m",
                "pytest",
                "-q",
                "tests",
                "--junitxml",
                str(output / "tests.xml"),
            ],
            log=output / "tests.txt",
            cwd=work,
            env=env,
        )
        report = ET.parse(output / "tests.xml").getroot()
        cases = list(report.iter("testcase"))
        if len(cases) != int(match[1]) or any(list(c) for c in cases):
            raise AssertionError("Missing, skipped, failed or errored paired test")
        summary = call(
            [str(python), "-I", "-m", "gat.demo.surface_inspection", str(output / "example")],
            log=output / "example.txt",
            cwd=work,
            env=env,
        )
        wheel_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in distributions}
        retained = output / "dist"
        retained.mkdir()
        for path in distributions:
            shutil.copyfile(path, retained / path.name)
    for key, path in (("cse", cse), ("csg", csg)):
        if call(["git", "-C", str(path), "rev-parse", "HEAD"]).strip() != revisions[key]:
            raise AssertionError("A source revision changed during qualification")
        call(["git", "-C", str(path), "diff", "--exit-code"])
    payload = {
        "source_revisions": revisions,
        "installed_tests": len(cases),
        "skipped": 0,
        "failed": 0,
        "wheel_sha256": wheel_hashes,
        "example": json.loads(summary),
        "physical_validation": "not_performed",
        "cryptographic_verification": "not_performed",
    }
    (output / "qualification.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
