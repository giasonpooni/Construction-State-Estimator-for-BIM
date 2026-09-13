"""Reports are inert; instruments are self-contained. Both, enforced.

``docs/design-language-v1.md`` divides every human surface into two classes,
and the README states the division as a fact a reader can rely on:

* a **report** carries no scripts and fetches nothing, so one attached to an
  RFI or pulled out of an archive cannot change meaning or behaviour;
* an **instrument** may carry its own inline scripts, under the same
  isolation: one file, no network, no external resource.

Both halves were already tested, but each only on its own half of the
surfaces -- reports for scripts, instruments for URLs. A claim the README
makes about all five belongs in one place that checks all five.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest

import gat.demo
from gat import ObserveQuantity
from gat.geometry.viewer import export_viewer_html
from gat.headless import handle_request
from gat.ifc_audit import audit_ifc_file
from gat.report import decode_ledger, decode_response, render_html
from gat.session import GatSession
from gat.workbench import export_console_html

DEMO = os.path.dirname(gat.demo.__file__)
MODEL = os.path.join(DEMO, "model.ifc")
BEAM = os.path.join(DEMO, "beam_model.ifc")

#: XML namespace URIs. These name a vocabulary and are never dereferenced, so
#: an inline ``<svg xmlns="http://www.w3.org/2000/svg">`` is not a fetch --
#: exempted by exact value rather than by pattern, so a real w3.org request
#: would still be caught.
_NAMESPACE_URIS = (
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/1999/xhtml",
)

#: Anything that would reach outside the one file it is written to.
_OUTBOUND = re.compile(
    r"https?://|\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|importScripts"
    r"|navigator\.sendBeacon"
)


def _outbound(html: str) -> list[str]:
    for uri in _NAMESPACE_URIS:
        html = html.replace(uri, "")
    return _OUTBOUND.findall(html)


def _surfaces(tmp: str) -> dict[str, tuple[str, str]]:
    """Every shipped HTML surface, as (class, document)."""
    session = GatSession.load_ifc(MODEL)
    session.run(ObserveQuantity.single(session.var("Office-A", "Volume"), 59.4, 0.05))
    ledger_path = os.path.join(tmp, "ledger.json")
    session.export_ledger(ledger_path)

    response = handle_request(
        {
            "format": "gat-headless-request-v1",
            "request_id": "surface-class-check",
            "operation": "beam_assurance",
            "state": {"kind": "ifc", "path": BEAM},
            "payload": {
                "case_id": "surface-class",
                "beam_name": "Beam-B1",
                "factored_demand_n_m": 301000.0,
                "confidence": 0.95,
                "material_certificate_path": os.path.join(
                    DEMO, "material_certificate.json"
                ),
            },
        }
    )
    console_path = os.path.join(tmp, "console.html")
    export_console_html(session.world, console_path, model_name="model.ifc", n=2)
    viewer_path = os.path.join(tmp, "viewer.html")
    export_viewer_html(session.world, viewer_path, model_name="model.ifc", n=2)

    def read(path: str) -> str:
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    return {
        "gat report": ("report", render_html(decode_response(response))),
        "gat ledger": ("report", render_html(decode_ledger(ledger_path))),
        "gat audit --html": (
            "report",
            render_html(decode_response(audit_ifc_file(MODEL).to_dict())),
        ),
        "gat console": ("instrument", read(console_path)),
        "gat view": ("instrument", read(viewer_path)),
    }


class SurfaceClassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.surfaces = _surfaces(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_every_shipped_surface_is_covered(self) -> None:
        """A new surface must be classified here, not quietly exempt."""
        self.assertEqual(
            set(self.surfaces),
            {"gat report", "gat ledger", "gat audit --html", "gat console", "gat view"},
        )

    def test_a_report_carries_no_script(self) -> None:
        for name, (surface_class, html) in self.surfaces.items():
            if surface_class != "report":
                continue
            with self.subTest(surface=name):
                self.assertNotIn("<script", html.lower())

    def test_an_instrument_carries_its_own_script(self) -> None:
        """Stated so the class is a real division, not a lenient one."""
        for name, (surface_class, html) in self.surfaces.items():
            if surface_class != "instrument":
                continue
            with self.subTest(surface=name):
                self.assertIn("<script", html.lower())

    def test_nothing_reaches_outside_its_own_file(self) -> None:
        """The isolation both classes share: no network, no external resource."""
        for name, (_, html) in self.surfaces.items():
            with self.subTest(surface=name):
                found = _outbound(html)
                self.assertEqual(
                    found, [], f"{name} would reach outside the file: {found[:3]}"
                )


if __name__ == "__main__":
    unittest.main()
