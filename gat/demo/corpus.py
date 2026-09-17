"""List I or needle a free coordinate.

    python -m gat.demo.corpus
    python -m gat.demo.corpus needle var.opening-width
"""

from __future__ import annotations

import argparse
import json

from gat.corpus import CorpusError, load_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Invariant corpus: list I or needle x")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "needle"])
    parser.add_argument("ident", nargs="?")
    args = parser.parse_args()
    corpus = load_corpus()
    if args.command == "list":
        print(json.dumps({
            "schema": corpus.document["schema"],
            "invariants": [row.get("id") for row in corpus.invariants],
            "free_coordinates": [row.get("id") for row in corpus.free_coordinates],
            "global_ids": sorted(corpus.global_ids()),
        }, indent=2))
        return
    if not args.ident:
        raise SystemExit("needle requires an id")
    try:
        print(json.dumps(corpus.needle(args.ident), indent=2, default=str))
    except CorpusError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
