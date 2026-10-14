# Command line

```bash
pip install bimdelta
```

Installs the `bimdelta` command and the diff engine, `bimdelta-core`. Python 3.10 or newer;
IfcOpenShell wheels exist for Windows, macOS and Linux, so no compiler is needed.

Unlike the web app, the command line has no file size limit.

## `bimdelta diff V1 V2`

Compares two versions of a model. Each version is a file, or `REV:PATH` for a committed one,
so `bimdelta diff HEAD~1:model.ifc model.ifc` compares the last commit with the working copy.
Git LFS content is fetched from the local store.

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

A take-off of both versions and the change, per IFC class (`--by class`, default), material
(`--by material`) or storey (`--by storey`): element count, length (m), area (m²), volume (m³)
and weight (kg). Columns that are zero in both versions are left out. `--changed-only` keeps
the groups whose quantities changed. Formats as for `diff`.

```text
$ bimdelta quantities HEAD~1:model.ifc HEAD:model.ifc --by material --changed-only
| Material                     |      Count |           Length m |             Area m² |          Volume m³ |
| Concrete, Cast-in-Place gray | 194 (-25)  | 759.66 (-128.01)   | 9,934.14 (-550.63)  | 2,639.40 (-108.55) |
```

Values come from the quantity sets in the files (e.g. `Qto_WallBaseQuantities`); nothing is
measured from geometry. For each element the first available net quantity is used, then the
gross one, converted with the file's own units. **In Revit, turn on *Export base quantities*
in the IFC export settings** (the [add-in](revit-addin-install.md) does); elements without
quantities are counted and reported.

By material, a layered or composite element's volume and weight are split between its
materials by layer thickness or constituent fraction. Its count, length and area count in full
for each material it contains, so those columns do not add up to the total row.

`bimdelta diff` and `bimdelta review` include the same take-off: `diff --format json` has it as
`quantities`, the Markdown outputs add a line such as
`Quantities: Concrete -108.55 m³ · Steel +400 kg`, and the viewer has a Quantities tab.

## `bimdelta review BASE [HEAD]`

One report for every IFC file added, deleted, modified or renamed between two revisions (`HEAD`
by default), e.g. the two ends of a pull request:

```bash
bimdelta review origin/main
bimdelta review main feature/level-3 -f json -o review.json
```

Markdown (default) has a section per file: totals, a per-class table, the per-storey counts and
changed elements in collapsible blocks. This is what the [GitHub Action](github-action.md)
posts.

| Option | |
|---|---|
| `-f, --format markdown\|json` | JSON holds each file's status and full `DiffResult` |
| `-o, --output FILE` | Write to a file instead of standard output |
| `--viewer-url URL --github-repo OWNER/NAME` | Add "View 3D diff" links for files in a public GitHub repository; `--head-repo` when the head commit is in a fork |
| `--limit N` | Most elements listed per change type (default 50) |
| `--max-chars N` | Leave out detail until the Markdown fits, e.g. `60000` for a GitHub comment |
| `--exit-code` | Exit with 1 if any model changed |
| `--repo`, `--strict`, `--config` | As for the other commands |

## `bimdelta serve`

Opens a repository's history in the 3D viewer, on your machine:

```bash
cd my-project
bimdelta serve
```

The browser shows a timeline of the commits that touched each IFC file, plus the working copy
when it has uncommitted changes. Click a point to compare it with the one before, shift-click
to choose the other end, or step through history with the arrow keys. Selecting an element
shows its changes grouped into Geometry, Type, Material and Properties, and its **History**:
every commit that added, changed or removed it, by whom and with which message (the same as
`bimdelta blame`).

| Option | |
|---|---|
| `--repo DIR` | Repository to serve (default: current directory) |
| `--port N` | Port on 127.0.0.1; `0` (default) picks a free one |
| `--no-open` | Do not open a browser |
| `--strict`, `--config` | As for the other commands |

The server listens on 127.0.0.1 only and answers only requests addressed to it, so other
machines and other web pages cannot read the repository through it. Comparisons are cached in
`.git/bimdelta-cache/`; the first look at a pair of versions takes as long as `bimdelta diff`,
later ones are instant. The Revit add-in's **Open Diff Viewer** runs this command.

## Git commands

`bimdelta install-git-driver`, `bimdelta textconv` and the hidden `bimdelta git-diff` are
described in [Git integration](git-integration.md).
