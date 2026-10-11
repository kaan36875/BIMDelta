# Recorded round-trip exports

Real IFC export pairs for the round-trip battery. Each scenario is a folder with `v1.ifc`,
`v2.ifc` and `expected.json`; `pytest packages/bimdelta-core -k recorded` checks them.

See [docs/globalid-stability.md](../../docs/globalid-stability.md) for the scenarios and how to
record them.
