# GitHub Action

When a pull request changes an IFC file, the BIMDelta action comments with what changed:
per-class and per-storey counts, the changed elements, and a **View 3D diff** link that opens
both versions in the viewer with changes colour-coded. Later pushes edit the same comment.

## Setup

Add `.github/workflows/bimdelta.yml`:

```yaml
name: BIMDelta

on:
  pull_request:
    paths: ["**/*.ifc", "**/*.IFC"]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: kaan36875/BIMDelta/apps/github-action@v0.5.0
```

That is all: the action finds the pull request's base and head commits, fetches them if the
checkout does not contain them, and compares every IFC file that differs. A
[`.bimdelta.yml`](cli.md#settings) at the repository root is used if present.

The `paths` filter skips the job for pull requests that touch no model. Leave it out if a
comment should also be corrected after a push that reverts every model change.

## Inputs

| Input | Default | |
|---|---|---|
| `base-ref` | PR base commit | Revision to compare from |
| `head-ref` | PR head commit | Revision to compare to |
| `lfs` | `true` | Fetch Git LFS objects for both revisions |
| `comment-mode` | `sticky` | `sticky` edits one comment, `new` adds one per run, `off` only writes the job summary |
| `viewer-base-url` | `https://bimdelta.vercel.app` | Viewer for the 3D links; empty to leave them out |
| `config` | | Settings file, instead of `.bimdelta.yml` |
| `strict` | `false` | Turn the [noise filter](noise-filter.md) off |
| `github-token` | `github.token` | Token used to comment |
| `python-version` | `3.12` | |

## Outputs

| Output | |
|---|---|
| `changed-files` | Number of IFC files that differ |
| `has-changes` | `true` if any element was added, removed or modified |
| `report` | Path of the Markdown report |

`has-changes` can gate later steps, e.g. requiring a BIM coordinator's review only when the model
actually changed rather than when it was merely re-exported.

## Behaviour

- **Every run writes the report to the job summary**, whatever `comment-mode` says.
- **Large reports** are shortened to fit GitHub's comment size: element lists first, then the
  per-storey tables. The class totals always stay.
- **Pull requests from forks** get a read-only token under `pull_request`, so the action cannot
  comment; it prints a warning and the report stays in the job summary. Do not switch to
  `pull_request_target` to get around this: it runs with write access on code from the fork.
- **Private repositories** get the comment without 3D links. The hosted viewer downloads
  models from `raw.githubusercontent.com`, which only serves public files, so the link would
  not open.
- **Git LFS**: with `lfs: true` the action runs `git lfs fetch` for both commits. Links to
  LFS-stored files point to `media.githubusercontent.com`, which serves their content.
- **Everything shown is escaped.** Element names, property values and file names come from the
  pull request, so they are escaped before going into the comment's Markdown; a crafted model
  cannot inject links, images or HTML.

## The viewer's URL mode

The link has the form

```text
https://bimdelta.vercel.app/?v1_url=<raw file URL>&v2_url=<raw file URL>
```

and works for any two public files on `raw.githubusercontent.com` or
`media.githubusercontent.com`, not only from the action. The browser downloads both files for the
3D view and the server downloads them again to compute the diff; the server fetches nothing but
those two hosts. The hosted viewer is limited to 50 MB per file; use the
[command line](cli.md) for bigger models.

## Without GitHub

The action is a thin wrapper around `bimdelta review BASE HEAD`, which prints the same
report for any two revisions:

```bash
bimdelta review origin/main HEAD > review.md
```

Any CI system can post that file wherever reviews happen.
