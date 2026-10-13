# Command line

```bash
pip install bimdelta
```

Installs the `bimdelta` command and the diff engine, `bimdelta-core`. Python 3.10 or newer;
IfcOpenShell wheels exist for Windows, macOS and Linux, so no compiler is needed.

Unlike the web app, the command line has no file size limit.

## `bimdelta diff V1 V2`

Compares two versions of a model.

| Option | |
|---|---|
| `-f, --format table\|markdown\|json` | `table` (default) for the terminal, `markdown` for pull requests and reports, `json` for scripts |
| `--summary-only` | Counts only. With `json`, prints the `DiffSummary` object instead of the whole result |
| `--filter EXPR` | Keep only matching elements; see below |
| `--strict` | Turn the [noise filter](noise-filter.md) off |
| `--config FILE` | Settings file; see below |
| `--limit N` | Most elements listed by `table` and `markdown` (default 100, `0` for all). JSON is never truncated |
| `--exit-code` | Exit with 1 when there are changes, like `git diff --exit-code` |

`--format json` prints a `DiffResult` exactly as the HTTP API returns it, with
`schema_version` at the top. Unchanged elements are included.

### Filters

```bash
bimdelta diff a.ifc b.ifc --filter "class=IfcWall*,storey=Level 1"
bimdelta diff a.ifc b.ifc --filter "change=added,change=removed"
```

Terms are `key=value` separated by commas. Terms with the same key are alternatives, different
keys must all match. Matching ignores case and accepts `*` and `?`.

| Key | Matches |
|---|---|
| `class` | IFC class, e.g. `IfcWall`, `IfcWall*` |
| `storey` | Storey name, before or after the change |
| `change` | `added`, `removed`, `modified`, `unchanged` |
| `name` | Element name, before or after the change |
| `id` | GlobalId in either version |

The summary counts are recomputed for the filtered elements. Model totals (`total_v1`,
`total_v2`), storey elevation changes and the noise report describe the whole models and stay
as they are.

### Settings

Without `--config`, the nearest `.bimdelta.yml` in the current directory or a parent is used,
so a file at the repository root applies to every command run inside it. All keys are optional:

```yaml
# .bimdelta.yml
placement_translation_tolerance: 0.001   # metres
fallback_placement_tolerance: 0.05       # metres
include_openings: false
ignore_properties:
  - "*.Edited by"
  - "Pset_Revit_*.Phase Created"
```

Settings can also come from `BIMDELTA_*` environment variables. Precedence, highest first:
command-line flags, the settings file, environment, defaults. An unknown key is an error.

### Exit status

| | |
|---|---|
| 0 | Compared (with or without changes, unless `--exit-code`) |
| 1 | Changes found and `--exit-code` given |
| 2 | Error: unreadable file, bad filter, invalid settings |

## `bimdelta blame GLOBALID [PATH]`

Lists the commits that added, modified or removed one element, newest first:

```text
$ bimdelta blame 0EubtQigr1vhxE6wY0hhn3
modified    da50d532f9  2026-10-13  Alice  "Move wall 100 mm"  IfcWall Basic Wall:Concrete 12":1524231
            moved
added       562eb6c2fc  2026-10-12  Alice  "Initial model"  IfcWall Basic Wall:Concrete 12":1524231
```

`PATH` can be left out when the repository tracks a single `.ifc` file. Options: `--repo DIR`,
`--rev REV` (start somewhere other than `HEAD`), `--max-commits N`, `--format
table|markdown|json`, `--strict`, `--config`.

Consecutive versions are compared with the same engine as `bimdelta diff`, so the element is
followed through a re-export that changed its GlobalId (matched by Tag or placement). Such a
step is shown as `reidentified` when nothing else changed.

Each comparison is cached in `.git/bimdelta-cache/`, keyed by the two Git blob ids and the
settings. The first run over a long history takes about as long as diffing every pair of
versions; later runs, for any element of the same file, read the cache. Delete the directory
to clear it. Renames are not followed: history starts at the commit that created the file
under its current path.

## `bimdelta quantities V1 V2`

Totals per IFC class (`--by class`, default) or per material (`--by material`), for both
versions and the change: element count, length (m), area (m²) and volume (m³). Formats as
for `diff`.

Values come from the quantity sets in the files (e.g. `Qto_WallBaseQuantities`); nothing is
measured from geometry. For each element the first available net quantity is used, then the
gross one. Elements without quantities are counted and reported: in Revit, turn on base
quantities in the IFC export settings. This command is a first version; per-layer
material splits and geometry-based take-off will follow.

## Git commands

`bimdelta install-git-driver`, `bimdelta textconv` and the hidden `bimdelta git-diff` are
described in [Git integration](git-integration.md).
