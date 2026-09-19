#!/usr/bin/env python3
"""Compare the live GitHub About panel against .github/repo-about.json.

GITHUB_TOKEN can read repository metadata but cannot PATCH the description
or topics: that needs administration:write, which the Actions token is never
granted, so the fix stays a human step. What this script does is stop the
drift from being silent -- it names every field that differs and prints the
exact commands that correct it.

stdlib only, to match the rest of the repo.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
_ROOT = Path(__file__).resolve().parents[1]
INTENDED = _ROOT / ".github" / "repo-about.json"


def _get(url: str, token: str | None) -> dict:
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def compare(intended: dict, live: dict) -> list[str]:
    """Field names that differ. Topics compare as sets, text exactly."""
    drift: list[str] = []
    if (live.get("description") or "") != (intended.get("description") or ""):
        drift.append("description")
    if set(live.get("topics") or []) != set(intended.get("topics") or []):
        drift.append("topics")
    if "homepage" in intended and (live.get("homepage") or "") != (
        intended.get("homepage") or ""
    ):
        drift.append("homepage")
    return drift


def _render_fix(slug: str, intended: dict, live: dict, drift: list[str]) -> str:
    lines = ["", "To correct it (needs a human, or a PAT with repo scope):", ""]
    if "description" in drift or "homepage" in drift:
        lines.append(
            f"  gh repo edit {slug} \\\n"
            f"    --description {json.dumps(intended['description'])} \\\n"
            f"    --homepage {json.dumps(intended.get('homepage', ''))}"
        )
    if "topics" in drift:
        want = sorted(intended.get("topics") or [])
        have = sorted(live.get("topics") or [])
        flags = [f"--add-topic {t}" for t in want if t not in have]
        flags += [f"--remove-topic {t}" for t in have if t not in want]
        lines.append(f"  gh repo edit {slug} \\\n    " + " \\\n    ".join(flags))
    lines.append("")
    lines.append("  # or in the browser: the About panel's gear icon on")
    lines.append(f"  #   https://github.com/{slug}")
    return "\n".join(lines)


def main() -> int:
    intended = json.loads(INTENDED.read_text(encoding="utf-8"))
    slug = os.environ.get("GITHUB_REPOSITORY")
    if not slug:
        homepage = intended.get("homepage", "")
        marker = "github.com/"
        if marker not in homepage:
            print("set GITHUB_REPOSITORY=owner/repo", file=sys.stderr)
            return 2
        slug = homepage.split(marker, 1)[1].strip("/")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        live = _get(f"{API}/repos/{slug}", token)
    except urllib.error.HTTPError as error:
        print(f"could not read {slug} metadata: HTTP {error.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as error:
        print(f"could not reach the GitHub API: {error.reason}", file=sys.stderr)
        return 2

    print(f"repository: {slug}")
    print(f"  intended description: {intended.get('description')!r}")
    print(f"  live     description: {live.get('description')!r}")
    print(f"  intended topics     : {sorted(intended.get('topics') or [])}")
    print(f"  live     topics     : {sorted(live.get('topics') or [])}")

    drift = compare(intended, live)
    if not drift:
        print("\nAbout matches .github/repo-about.json.")
        return 0

    print(f"\nAbout has drifted from .github/repo-about.json: {', '.join(drift)}")
    print(_render_fix(slug, intended, live, drift))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
