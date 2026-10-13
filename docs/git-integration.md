# Git integration

Git treats an IFC file as text, so `git diff model.ifc` normally prints thousands of changed
STEP lines: entity ids are renumbered on every export. BIMDelta registers itself as the diff
driver for `*.ifc`, so Git shows element changes instead.

## Setup

```bash
pip install bimdelta
cd my-project
bimdelta install-git-driver
git add .gitattributes && git commit -m "Diff IFC files with BIMDelta"
```

This does two things:

1. Adds `*.ifc diff=ifc` to `.gitattributes`. Commit it: it tells every clone which files use
   the driver.
2. Writes the driver into the repository's `.git/config`:

   ```ini
   [diff "ifc"]
       command = bimdelta git-diff
       textconv = bimdelta textconv
       xfuncname = ^Ifc[A-Za-z]+ .*$
   ```

   `.git/config` is not shared, so each clone runs `bimdelta install-git-driver` once. Use
   `--global` to configure it once per user for every repository instead (the attribute then
   goes to Git's global attributes file, `~/.config/git/attributes` unless
   `core.attributesFile` says otherwise).

If `bimdelta` is not on `PATH` when you run the installer, e.g. it lives in a virtual
environment you activated only for the install, the driver is written with the full path of
that Python interpreter so it works from any shell. Override it with `--command`. Remove the
configuration with `bimdelta install-git-driver --uninstall`.

## What each Git command shows

**`git diff`** (working tree, `--cached`, or between commits) runs the external driver
(`command`). Git passes it both versions of the file, so the output is the full element diff
from the engine, as Markdown:

```text
$ git diff HEAD~1 -- model.ifc
diff --bimdelta a/model.ifc b/model.ifc
### BIMDelta: model.ifc

| Class | Added | Removed | Modified | Unchanged |
|---|---:|---:|---:|---:|
| **Total** | 0 | 0 | 1 | 1327 |
| IfcWall | 0 | 0 | 1 | 58 |

#### Modified (1)

- `IfcWall` **Basic Wall:Concrete 12":1524231** (L5) `0EubtQigr1vhxE6wY0hhn3` — moved
```

**`git log -p`, `git show`** and `git diff --no-ext-diff` do not run external drivers. They
use `textconv`, which turns each version into stable text (one header line per element, sorted,
followed by its type, placement, a geometry hash and its properties), and Git line-diffs that:

```diff
 IfcWall 0EubtQigr1vhxE6wY0hhn3  Basic Wall:Concrete 12":1524231  @ L5
     tag: 1524231
     type: Basic Wall:Concrete 12"
-    placement: 417599.142, 78709.211, 255.676
+    placement: 417599.232, 78709.255, 255.676
     geometry: a396d17242fa
```

The text form sees one version at a time, so it cannot match elements whose GlobalId changed
or hide property sets that only one export contains. Use `git diff` or `bimdelta diff` for the
matched, noise-filtered result. Pass `--ext-diff` to `git log -p` or `git show` to get it there
too.

The [settings file](cli.md#settings) at the repository root applies to both.

If a version cannot be read, the driver prints a one-line message in place of the diff
instead of failing, so one broken file does not stop `git log -p`.

## Large files and Git LFS

Exported models grow quickly; GitHub rejects files over 100 MB and warns from 50 MB. Git LFS
stores the file content outside the repository history:

```bash
git lfs install
git lfs track "*.ifc"
bimdelta install-git-driver
git add .gitattributes
```

`git lfs track` writes `*.ifc filter=lfs diff=lfs merge=lfs -text`. `install-git-driver` keeps
the LFS attributes and replaces `diff=lfs` with `diff=ifc`, giving:

```text
*.ifc filter=lfs merge=lfs -text diff=ifc
```

Run the installer after `git lfs track`; running `git lfs track` again later puts `diff=lfs`
back.

Git hands diff drivers the stored blob, which for an LFS file is a small pointer. BIMDelta
recognises pointers and fetches the content with `git lfs smudge`, which needs the object in
the local LFS store. Versions you have checked out are there; for older commits run
`git lfs fetch --all` (or `git lfs fetch origin <rev>`) first. The same applies to
`bimdelta blame`.

Hosting quotas are the usual concern with LFS: storage and bandwidth are metered per account,
and every pushed version of a model counts. Self-hosted LFS servers (Gitea,
GitLab, or a standalone server such as `lfs-test-server`) avoid the quota. Files under 50 MB
do not need LFS at all.
