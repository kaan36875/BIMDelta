# bimdelta-core

Element-level diff engine for IFC building models, built on [IfcOpenShell](https://ifcopenshell.org).

```python
from bimdelta_core import load_settings, run_diff

result = run_diff("rev-a.ifc", "rev-a.ifc", "rev-b.ifc", "rev-b.ifc", load_settings())
print(result.summary.added, result.summary.removed, result.summary.modified)
print(result.model_dump_json(indent=2))
```

Elements are matched by `GlobalId`, then by the authoring tool's element id in `IfcElement.Tag`,
then by class, name, storey and placement. Matched pairs are compared on properties and
quantities, placement, type, storey and a geometry signature (bounding box and volume).

A noise filter keeps export artefacts out of the result; see
[docs/noise-filter.md](https://github.com/kaan36875/BIMDelta/blob/main/docs/noise-filter.md).

Part of [BIMDelta](https://github.com/kaan36875/BIMDelta). MIT licensed.
