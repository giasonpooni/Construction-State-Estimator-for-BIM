# Map

```mermaid
flowchart TD
  IFC["IFC entity ≠ mesh"] --> W["World W + ledger"]
  W --> Bind["cse-point-bind-v1"]
  Bind --> Obs["ObserveQuantity / ObserveLinearized"]
  Obs --> Tickets["REQUEST_EVIDENCE tickets"]
  Tickets --> Split{"inspectability vs headless"}
  Split -->|presentable| IA["inspectability ACCEPT"]
  Split -->|no cal / no stamp"| HE["headless REQUEST_EVIDENCE"]
  W --> USD["OpenUSD projection · suitcase"]
  USD -.-> W
```

Caption: USD is a view. Blender does not mutate W. A green opening is not
a calibration certificate. `may_authorize` stays false until external
traceable σ and a human signature exist.
