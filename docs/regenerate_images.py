"""Regenerate every screenshot in docs/images from the running tool.

The README's images are output, not decoration: each one is a real artifact
this repository produced, captured from the real instrument. They go stale the
moment a surface changes, so they are regenerated rather than maintained.

    pip install playwright          # the driver only; a browser is required
    python docs/regenerate_images.py

The browser is found at ``--chrome``, ``$GAT_DOCS_CHROME``, or the first
Chromium under ``$PLAYWRIGHT_BROWSERS_PATH``. Nothing here is imported by the
package and nothing runs in CI: it is a documentation tool.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGES = REPO / "docs" / "images"
SCALE = 1.5


# -- the terminal panels ----------------------------------------------------


TERMINAL_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0d1117;font:14px/1.55 "IBM Plex Mono",ui-monospace,
     SFMono-Regular,Consolas,monospace}
.bar{display:flex;gap:7px;align-items:center;padding:11px 15px;
     background:#161b22;border-bottom:1px solid #21262d}
.dot{width:11px;height:11px;border-radius:50%}
.t{margin-left:11px;color:#7d8590;font-size:12px;letter-spacing:.03em}
.body{padding:18px 22px 22px}
.blk{margin-bottom:20px}.blk:last-child{margin-bottom:0}
.cmd{color:#e6edf3;font-weight:500;margin-bottom:7px;white-space:pre-wrap}
.p{color:#3fb950;margin-right:9px;font-weight:600}
pre{margin:0;color:#adbac7;white-space:pre-wrap;word-break:break-word}
"""


def terminal_page(title: str, runs: list[tuple[str, str]]) -> str:
    blocks = []
    for command, output in runs:
        blocks.append(
            f'<div class="blk"><div class="cmd"><span class="p">$</span>'
            f"{html.escape(command)}</div>"
            f"<pre>{html.escape(output.rstrip())}</pre></div>"
        )
    dots = "".join(
        f'<span class="dot" style="background:{c}"></span>'
        for c in ("#ff5f57", "#febc2e", "#28c840")
    )
    return (
        f"<title>{html.escape(title)}</title><style>{TERMINAL_CSS}</style>"
        f'<div class="bar">{dots}<span class="t">{html.escape(title)}</span></div>'
        f'<div class="body">{"".join(blocks)}</div>'
    )


def run(command: str, limit: int = 24, verdict: bool = False) -> str:
    """Run a documented command and keep what the reader would see.

    ``verdict`` keeps the head of the output *and* its closing disposition
    line, which is the part that matters and the part a head-truncation
    always cuts.
    """
    result = subprocess.run(
        command, shell=True, cwd=REPO, capture_output=True, text=True, timeout=900
    )
    lines = (result.stdout or result.stderr).strip().split("\n")
    if not verdict or len(lines) <= limit:
        return "\n".join(lines[:limit])
    closing = [line for line in lines if line.startswith("->")]
    kept = lines[: max(1, limit - len(closing) - 1)]
    return "\n".join(kept + [f"  ... {len(lines) - len(kept) - len(closing)} more rows"] + closing)


# -- the artifacts ----------------------------------------------------------


def build_artifacts(work: Path) -> dict[str, Path]:
    """Produce the real HTML surfaces the screenshots are taken of."""
    import gat.demo
    from gat import GatSession, ObserveQuantity, SetParameter
    from gat.headless import handle_request

    demo = Path(gat.demo.__file__).parent
    model, beam = demo / "model.ifc", demo / "beam_model.ifc"

    # A ledger with real transitions, for TIME mode and the ledger surface.
    session = GatSession.load_ifc(str(model))
    session.run(
        ObserveQuantity.single(session.var("Office-A", "Volume"), 59.4, 0.05)
    )
    session.run(
        SetParameter(session.var("Level 1", "ClearHeight"), 3.4, design_sigma=0.01)
    )
    ledger = work / "ledger.json"
    session.export_ledger(str(ledger))

    # A real beam capacity decision through the headless boundary.
    request = {
        "format": "gat-headless-request-v1",
        "request_id": "readme-beam",
        "operation": "beam_assurance",
        "state": {"kind": "ifc", "path": str(beam)},
        "payload": {
            "case_id": "beam-b1-certificate",
            "beam_name": "Beam-B1",
            "factored_demand_n_m": 301000.0,
            "confidence": 0.95,
            "material_certificate_path": str(demo / "material_certificate.json"),
        },
    }
    response = work / "response.json"
    response.write_text(json.dumps(handle_request(request), indent=1))

    console, report, ledger_html = (
        work / "console.html",
        work / "report.html",
        work / "ledger.html",
    )
    for command in (
        f'gat console gat/demo/model.ifc -o "{console}" --variations 3 --ledger "{ledger}"',
        f'gat report "{response}" --html -o "{report}"',
        f'gat ledger "{ledger}" --html -o "{ledger_html}"',
    ):
        subprocess.run(command, shell=True, cwd=REPO, check=True, capture_output=True)

    # The terminal panels, from commands the README actually documents.
    starts = [
        (
            "gat audit gat/demo/beam_model.ifc --text",
            run("gat audit gat/demo/beam_model.ifc --text", 18),
        ),
        (
            'gat inspect gat/demo/model.ifc --var "Level 1.TotalWallCost"',
            run('gat inspect gat/demo/model.ifc --var "Level 1.TotalWallCost"', 22),
        ),
    ]
    decide = [("python -m gat.demo.workflow", run("python -m gat.demo.workflow", 24))]
    closed = _fail_closed_panel(work, demo)

    start_html = work / "term_start.html"
    decide_html = work / "term_decide.html"
    closed_html = work / "term_closed.html"
    start_html.write_text(terminal_page("gat — audit and inspect", starts))
    decide_html.write_text(terminal_page("gat — one decision, three ways", decide))
    closed_html.write_text(terminal_page("gat — three ways to not pass", closed))

    return {
        "console": console,
        "report": report,
        "ledger": ledger_html,
        "term_start": start_html,
        "term_decide": decide_html,
        "term_closed": closed_html,
    }


def _fail_closed_panel(work: Path, demo: Path) -> list[tuple[str, str]]:
    """Three refusals, each produced here rather than described.

    A pass, a world no compliance rule reached, and a carrier edited in a
    text editor. The middle and the last one both used to exit 0.
    """
    import re

    from gat import GatSession, ObserveQuantity

    session = GatSession.load_ifc(str(demo / "model.ifc"))
    session.run(
        ObserveQuantity.single(session.var("Office-A", "Volume"), 59.4, 0.05)
    )
    honest = work / "state.usda"
    session.export_usd(str(honest))

    text = honest.read_text(encoding="utf-8")
    height = re.search(r'"mu": \[([0-9.eE+-]+),', text).group(1)
    forged = work / "forged.usda"
    forged.write_text(
        text.replace(f'"mu": [{height},', '"mu": [8.0,', 1), encoding="utf-8"
    )

    return [
        (
            f"gat verify {honest.name}                      # the honest carrier",
            run(f'gat verify "{honest}"', 5, verdict=True),
        ),
        (
            "gat verify gat/demo/beam_model.ifc          # no rule reaches this world",
            run("gat verify gat/demo/beam_model.ifc", 4, verdict=True),
        ),
        (
            f"sed 's/{height}/8.0/' {honest.name} > {forged.name}   # raise a storey in an editor\n"
            f"$ gat verify {forged.name}",
            run(f'gat verify "{forged}"', 4),
        ),
    ]


def find_chrome(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("GAT_DOCS_CHROME")):
        if candidate:
            return candidate
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if root:
        for path in sorted(Path(root).glob("chromium-*/chrome-linux/chrome")):
            return str(path)
    raise SystemExit(
        "no Chromium found; pass --chrome or set GAT_DOCS_CHROME"
    )


def capture(pages: dict[str, Path], chrome: str) -> None:
    from playwright.sync_api import sync_playwright

    IMAGES.mkdir(parents=True, exist_ok=True)
    shots = [
        ("term_start", "cli-inspect.png", 980, 600, True, None, 1000),
        ("term_decide", "cli-decision.png", 980, 600, True, None, 1000),
        # A realization, not the nominal: the point of FIELD is that the
        # building is a belief, and a tidy nominal box does not show that.
        ("console", "console-field.png", 1500, 940, False, "FIELD~sample 2", 2500),
        ("console", "console-relations.png", 1500, 940, False, "RELATIONS", 2500),
        # A readout screenshot must show the reading, not the prompt to take
        # one: BELIEF with nothing selected is an empty card, and the README
        # claims it shows mean and sigma per quantity.
        ("console", "console-belief.png", 1500, 940, False, "BELIEF/Wall-Party", 2500),
        ("report", "report-verdict.png", 1100, 900, False, None, 1200),
        ("ledger", "ledger.png", 1100, 900, True, None, 1200),
        ("term_closed", "cli-fail-closed.png", 1020, 430, True, None, 1000),
    ]
    with sync_playwright() as driver:
        browser = driver.chromium.launch(
            executable_path=chrome,
            args=["--no-sandbox", "--disable-gpu", "--use-gl=swiftshader"],
        )
        for key, name, width, height, full, click, wait in shots:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=SCALE,
            )
            page.goto(pages[key].as_uri())
            page.wait_for_timeout(wait)
            if click:
                # "READOUT" switches the readout; "/x" then selects x in its
                # panel, and "~x" clicks x inside its sandboxed viewer frame.
                match = re.fullmatch(r"([A-Z]+)(?:([/~])(.+))?", click)
                readout, sep, target = match.group(1), match.group(2), match.group(3)
                # The readout name appears in the panel body too; only the tab
                # switches the instrument.
                page.get_by_role("tab", name=readout).click()
                page.wait_for_timeout(1200)
                if sep == "/":
                    # Scope to the visible panel: entity names also appear in
                    # the other readouts, which are hidden and unclickable.
                    page.locator(f'.panel[data-mode="{readout}"]').get_by_text(
                        target, exact=True
                    ).first.click()
                elif sep == "~":
                    page.frame_locator("#structure").get_by_text(
                        target, exact=True
                    ).first.click()
                page.wait_for_timeout(1500)
            page.screenshot(path=str(IMAGES / name), full_page=full)
            page.close()
            print(f"wrote docs/images/{name}")
        browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", help="path to a Chromium executable")
    args = parser.parse_args(argv)

    chrome = find_chrome(args.chrome)
    with tempfile.TemporaryDirectory() as tmp:
        capture(build_artifacts(Path(tmp)), chrome)
    print(f"\n{len(list(IMAGES.glob('*.png')))} images in docs/images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
