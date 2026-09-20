# License policy

Review status: proposed transition on `codex/role-based-licensing`.
Counsel, contributor-ownership, and scope review remain pending. This
review branch does not adopt a new license on the default branch. The
license scope below describes the proposed state; existing grants and
separately licensed material remain preserved.

## Proposed original project source

The original project source distributed with this notice is licensed under
the Mozilla Public License, version 2.0 (`MPL-2.0`), except for the separately
licensed material identified below or an explicit applicable file notice.
The complete unmodified license is in [LICENSE](LICENSE). This policy explains
scope; it does not alter the MPL or third-party terms.

This Source Code Form is subject to the terms of the Mozilla Public License,
v. 2.0. If a copy of the MPL was not distributed with this file, You can obtain
one at https://mozilla.org/MPL/2.0/.

## Legacy grant and attribution

The current pre-transition `main` baseline is
`7b6237d129d132328b6ef1db0fa83bb75f5b208f`.
The prepared review packet was originally based on
`7b55a5a24610743df0e691f182678d139d60d0e6`; that baseline
carried the same preserved MIT notice and its existing grants remain intact.
The earlier inspected main baseline
`e4486f92a4b8fbc67d92136b065216dd2027df6d` carried the same MIT license;
its prior permissions and attribution remain preserved as well.
The root license distributed at the current exact baseline is reproduced byte-for-byte
in [LICENSE-MIT](LICENSE-MIT), including this original notice:

> Copyright (c) 2026 Notation Systems

Previously granted MIT permissions remain in effect for copies and material
already distributed under MIT, subject to that license's notice conditions.
This change does not revoke those grants, rewrite history, or make previously
public code confidential. Preserve the legacy notice for carried legacy
material. No copyright ownership, contribution assignment, or contributor
consent is invented by this policy.

Previously published development branches retain their applicable prior
grants. This policy does not merge, rewrite, or relicense third-party
contributions by assertion.

## Separately licensed material

- `integrations/blender/gat_assurance/` retains the existing
  `GPL-3.0-or-later` declaration in `blender_manifest.toml`. The root MPL notice
  does not replace that declaration. Preserve the Blender extension's terms
  when building or distributing it.
- The external buildingSMART IFC models identified in
  `validation/ifc-corpus-v1.json` retain their recorded `CC-BY-4.0` terms and
  attribution requirements. They are retrieved separately; the root software
  license does not replace their data license.
- AISC, IBC, ADA, CSA, SDI, HMMA, ACI, manufacturer documentation, and other
  cited standards/reference works retain their owners' rights. Published
  numerical reference cases and citations do not confer a license over the
  underlying standards. The AISC source PDF is not vendored.
- External dependencies and their components, including optional
  IfcOpenShell/OpenUSD/cryptography and SP1 tooling, retain their own licenses
  and notices. Their rights are not replaced by repository package metadata.

## Public reference code and private deployment material

The public scope is general mathematical and scientific source, schemas,
synthetic test fixtures, and reusable reference interfaces. Customer-specific
adapters, real calibration certificates/profiles, credentials, site models,
observation logs, operational state, and customer evidence belong outside the
public repository unless separately authorized for publication.

A source-code license is not permission to publish customer data or secrets.
Conversely, calling an adapter private does not remove the MPL obligations
applicable to any covered source code it contains. No confidentiality claim
is made for material already published. Synthetic examples are reference
fixtures, not licensed access to a customer's measurements or installation.
