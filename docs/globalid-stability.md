# Element identity and the Revit round-trip battery

A diff is only useful if the same element is recognised as the same element in both files.
This document explains how BIMDelta matches elements, where that can go wrong with Revit
exports, and how to check it against real exports.

## How elements are matched

1. **GlobalId.** The IFC GUID. Authoring tools are expected to keep it stable for an element
   across exports.
2. **Tag.** `IfcElement.Tag` holds the authoring tool's own element id: Revit writes the
   ElementId, ArchiCAD its element GUID. If a GlobalId changed but the element still has the
   same class and tag, it is the same element. Only `(class, tag)` pairs that are unique in
   their file are used: Revit gives openings and some sub-elements the id of their host (one
   public Revit 2021 sample has 153 such duplicates).
3. **Placement fallback.** Remaining elements with the same class, name and storey, placed
   within 50 mm of each other, are paired nearest first. Pairs whose tags are both set and
   different are skipped: those are two different elements in the authoring tool, for example a
   wall that was deleted and redrawn in the same place.

The method used is reported per element as `match_method` (`global_id`, `tag` or `fallback`).

## The battery

Each scenario is something that happens in normal Revit work. Expected results:

| # | Scenario | Expected |
|---|---|---|
| 1 | Export the same model twice, no changes in between | 0 added, 0 removed, 0 modified |
| 2 | Export `v1`, save, close Revit, reopen the project, export `v2` (no edits) | 0 / 0 / 0 |
| 3 | Copy a wall, *Paste → Aligned to Same Place* | 1 added |
| 4 | Delete a wall and draw it again in the same place | 1 removed, 1 added |
| 5 | Move one wall by 100 mm | 1 modified (placement) |
| 6 | Same model, *Export Revit property sets* off, then on | 0 / 0 / 0, property sets listed as one-sided |
| 7 | Same model, *Export base quantities* off, then on | 0 / 0 / 0 |

`packages/bimdelta-core/tests/test_roundtrip.py` simulates every scenario with generated models
and runs in CI. Scenario 2 is additionally simulated as "the exporter regenerated every
GlobalId but kept the ElementIds", the case the tag pass exists for.

The simulation proves the logic. Only real exports prove the assumptions about Revit, so the
same test also runs on recorded exports.

## Results with Revit 2027

Recorded with Revit 2027 on Autodesk's *Snowdon Towers Sample Structural* project (IFC4 Reference
View, 1,328 elements), so the battery can be repeated with the same model. The exports themselves
are not in the repository.
"Without filter" is the same diff with `strict: true`.

| # | Result | Without filter |
|---|---|---|
| 1 | 0 / 0 / 0, every element matched by GlobalId | 0 / 0 / 0 |
| 2 | 0 / 0 / 0 | 0 / 0 / 0 |
| 3 | 1 added, original wall untouched | same |
| 4 | 1 removed, 1 added | same |
| 5 | 1 modified (placement) | same |
| 6 | 0 / 0 / 0, 26 property sets reported as only in v2 | 1,328 modified, 73,950 property differences |
| 7 | 0 / 0 / 0, 7 quantity sets reported as only in v2 | 1,239 modified, 6,025 property differences |

GlobalIds were stable across exports and across save and reopen. Revit 2027 names its parameter
property sets after the parameter groups (`Constraints`, `Identity Data`…) without a `PSet_Revit_`
prefix, which is why the filter works on presence rather than on names.

## Recording real exports

Use a small project (a few walls, a door, a floor is enough; keep files under ~10 MB so they can
live in the repository) and the same export setup for both files of a scenario, except where the
scenario changes it.

1. In Revit: *File → Export → IFC*. Pick one setup (for example *IFC4 Reference View*) and keep
   it for every scenario except 6 and 7.
2. For each scenario, save the export before the change as `v1.ifc` and after it as `v2.ifc`.
3. Put them in `samples/roundtrip/<number>-<name>/` together with an `expected.json`:

   ```
   samples/roundtrip/
     1-export-twice/        v1.ifc  v2.ifc  expected.json
     4-delete-redraw/       v1.ifc  v2.ifc  expected.json
   ```

   ```json
   { "added": 1, "removed": 1, "modified": 0 }
   ```

   Keys that are left out are not checked. An optional `"settings"` object is passed to
   `Settings`, e.g. `{ "settings": { "strict": true } }`.
4. Run:

   ```bash
   pytest packages/bimdelta-core -k recorded -v
   ```

   To keep large exports out of the repository, point `BIMDELTA_ROUNDTRIP_DIR` at another
   folder with the same layout.

When a scenario fails, the assertion message lists the properties that changed on the most
elements. That is usually the export artefact to add to the noise filter
(see [noise-filter.md](noise-filter.md)).

## Known limits

- An element moved by more than 50 mm *and* given a new GlobalId *and* without a usable tag is
  reported as removed and added.
- Elements without a name, storey or tag can only be matched by GlobalId and placement.
- Diffing exports of two different Revit files of the same building (for example after a
  model was rebuilt or split) matches almost nothing: both GlobalIds and ElementIds differ.
