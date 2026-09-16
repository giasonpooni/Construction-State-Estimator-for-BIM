"""Second SP1 host callback. Writes statement_digest. Does not stamp."""

from __future__ import annotations

import argparse
from pathlib import Path

from gat.sp1_kernel import host_callback, request_document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kernel SP1 callback: statement_digest, integrity-only"
    )
    parser.add_argument("output_directory", nargs="?", default="out/kernel-sp1")
    parser.add_argument("--executable")
    parser.add_argument("--prove", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()
    output = Path(args.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    request_path = output / "kernel_sp1_request.json"
    request_path.write_text(
        __import__("json").dumps(request_document(), indent=2, sort_keys=True) + "\n"
    )
    report = host_callback(
        args.executable,
        prove=args.prove,
        proof_path=output / "kernel-chain-jvp.proof",
        timeout_seconds=args.timeout,
    )
    report.write(output / "kernel_sp1_receipt.json")
    print(f"statement_digest {report.document['statement_digest']}")
    print(f"status {report.document['status']}")
    print(f"is_proof {report.is_proof}")
    print(f"claim_scope {report.document['claim_scope']}")


if __name__ == "__main__":
    main()
