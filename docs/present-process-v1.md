# Present process v1

The process has started. It does not end in a stamp.

```text
1. verify world          session.verify()
2. inventory identities  IfcSpace / IfcOpeningElement Guids
3. package gate          bind + declared calibration + observation
4. stamp                 always refused
```

```bash
python -m gat.demo.present_process --demo -o out/present-packet
python -m gat.demo.present_process --demo --lab --value 0.9 -o out/present-packet-lab
```

`--demo` writes the live packet with three open holes.
`--lab` fills bind + declared sigma + ObserveQuantity. Inspectability
may become ACCEPT. `04-stamp-refused.json` is still written.

Shipped snapshot of step 1 of the process:
[validation/present-packet-office-a/](../validation/present-packet-office-a/).
