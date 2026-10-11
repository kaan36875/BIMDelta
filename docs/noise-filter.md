# Noise filter

Exporting the same, unchanged model twice should produce an empty diff. In practice, IFC files
differ for reasons that have nothing to do with the design: different export settings, a
different exporter version, or metadata that changes on every save. If those differences show
up as element changes, a reviewer cannot find the real ones. The noise filter keeps them out of
the per-element result and reports them once, in the summary, so nothing is hidden silently.

All rules are switched off with `strict: true`.

## Rule 1: property sets present in only one file

If a property set exists on elements in one file but on **no** element in the other, it is
treated as an export difference, not as an edit to every element that carries it. Typical
causes:

- Revit's *Export Revit property sets* or *Export base quantities* option differs between the
  two exports.
- A different exporter version names Revit parameter groups differently (older exporters write
  `PSet_Revit_Constraints`, newer ones `Constraints`).
- Revit writes some property sets named after a family type and its element id
  (e.g. `M_Fixed:819mm x 759mm:...:147994`); duplicating or reloading the type renames them.

Such property sets are listed in `summary.noise.one_sided_psets` with the number of elements
that carry them, and are left out of the element comparison. The web viewer shows them under
the summary.

**Trade-off:** a property set that someone deliberately added to a few elements in the new
revision, and that exists nowhere in the old one, is reported in that summary list rather than
as a change on each of those elements. Run with `strict: true` to see it per element.

Volume quantities follow the same principle: an exported `NetVolume` or `GrossVolume` is only
used for the geometry comparison when both sides carry the same quantity. Otherwise both sides
use the volume computed from the shape, so turning *Export base quantities* on does not make
every element look reshaped.

## Rule 2: ignored properties

Glob patterns matched against `"<property set>.<property>"`, case-sensitive, with `*`, `?` and
`[abc]` wildcards. A difference in a matching property is not reported on the element; it is
counted in the element's `ignored_property_changes` and in `summary.noise.ignored_property_changes`.

Default list:

| Pattern | Why |
|---|---|
| `*.Edited by` | Revit worksharing: the user currently holding the element, not a property of the model. |

Setting `ignore_properties` replaces the default list, so include the defaults you want to keep.

### What is deliberately *not* ignored

Revit's own parameter property sets (`PSet_Revit_*`, or `Constraints`, `Dimensions`,
`Identity Data`… in newer exporters) are compared like any other property set. They hold design
data such as *Base Offset*, *Top Constraint*, *Unconnected Height* and *Host*, and a change to
those is a real change. They only stop being compared when they exist in just one of the files
(Rule 1).

## Transparency

Every diff result says what the filter did:

```jsonc
"summary": {
  "noise": {
    "strict": false,
    "ignore_properties": ["*.Edited by"],
    "ignored_property_changes": 3,       // differences hidden by either rule
    "one_sided_psets": [
      { "pset_name": "PSet_Revit_Phasing", "only_in": "v2", "element_count": 225 }
    ]
  },
  "top_changed_properties": [            // most frequently changed properties
    { "pset_name": "Constraints", "property_name": "Base Offset", "element_count": 412 }
  ]
}
```

`top_changed_properties` is the first thing to look at when a diff of an unchanged model is not
empty: a property that changed on hundreds of elements at once is usually an export artefact,
and a candidate for `ignore_properties`. Please open an issue with it, so the default list can
grow from real exports.

## Configuration

In a `.bimdelta.yml` file (unknown keys are rejected, so typos don't pass silently):

```yaml
strict: false
include_openings: false
ignore_properties:
  - "*.Edited by"
  - "Identity Data.Workset"
```

```python
from bimdelta_core import load_settings, run_diff

settings = load_settings(".bimdelta.yml")
```

or as environment variables, which the YAML file and explicit arguments override:

```bash
BIMDELTA_STRICT=true
BIMDELTA_IGNORE_PROPERTIES='["*.Edited by", "Identity Data.Workset"]'
```

## Numeric tolerances

| Setting | Default | Applies to |
|---|---|---|
| `float_tolerance` | 1e-5 | Numeric property and quantity values (in metres, m², m³ for measures) |
| `placement_translation_tolerance` | 1 mm | Element position relative to its storey |
| `placement_rotation_tolerance_deg` | 0.01° | Element orientation |
| `geometry_bbox_tolerance` | 1 mm | Bounding box dimensions |
| `geometry_volume_tolerance` | 1 cm³ | Volume |
| `fallback_placement_tolerance` | 50 mm | Matching elements whose ids changed |

Geometry is only tessellated when the IFC geometry of a matched pair is not identical; identical
geometry definitions are recognised from their content and skipped. Tessellations of curved
shapes written differently by two exporter versions can differ by more than 1 cm³; if that shows
up as geometry changes, raise `geometry_volume_tolerance`.
