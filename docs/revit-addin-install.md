# Revit add-in

The add-in puts version history on the Revit ribbon: **Save Version** exports the model to IFC
and commits it to a Git repository next to the `.rvt` file; **Share for Review** pushes the
versions to GitHub and opens a pull request for them; **Open Diff Viewer** shows the
saved versions on a timeline, the 3D diff between any two of them and each element's history.

Supported: Revit 2024, 2025, 2026 and 2027.

## Requirements

| | |
|---|---|
| **Git for Windows** | Required. [git-scm.com/download/win](https://git-scm.com/download/win). Git LFS is included and used when present. |
| **bimdelta** | For the change preview and the viewer: `pip install bimdelta` (Python 3.10 or newer). Save Version works without it, just without the preview. |
| **.NET SDK 8 or 10** | Only to build the add-in from source. |

## Install

From a clone of the repository, in PowerShell:

```powershell
cd revit
.\install.ps1                      # every installed Revit 2024-2027
.\install.ps1 -RevitVersion 2027   # one version
```

The script builds the add-in and copies it to
`%APPDATA%\Autodesk\Revit\Addins\<version>\`: the `BIMDelta.addin` manifest and a `BIMDelta`
folder with the assemblies. Start Revit; the first time, it asks whether to load the add-in
because it is not signed. Choose **Always Load**.

Remove it with `.\install.ps1 -Uninstall`.

If the Python on your `PATH` is shared with other tools, install `bimdelta` in its own
environment instead, so its dependencies do not change theirs, and point the add-in to it:

```powershell
py -m venv "$env:LOCALAPPDATA\BIMDelta\venv"
& "$env:LOCALAPPDATA\BIMDelta\venv\Scripts\python" -m pip install bimdelta
setx BIMDELTA_CLI "$env:LOCALAPPDATA\BIMDelta\venv\Scripts\bimdelta.exe"
```

Restart Revit after `setx`; a running Revit does not see the new variable. Update later with
`& "$env:LOCALAPPDATA\BIMDelta\venv\Scripts\python" -m pip install -U bimdelta`.

## Using it

1. Save the project (`.rvt`) somewhere it can stay, e.g. the project folder.
2. **BIMDelta → Save Version**. The first time, BIMDelta offers to create a Git repository in
   that folder.
3. The model is exported to `ifc/<project name>.ifc` with fixed settings: IFC4 Reference View,
   base quantities on, Revit property sets off, whole model rather than the active view. The
   export runs inside a transaction that is rolled back, so the Revit model is not changed.
4. A dialog shows what changed since the last version (from `bimdelta diff`) and asks what the
   change was. **Save version** commits it, with your Revit user name as the author.
5. **View changes**, or later **Open Diff Viewer**, opens the history. Click an element and
   choose **History** to see every version that touched it.

Only the IFC export is versioned. The `.rvt` file and Revit backups are listed in `.gitignore`:
Git handles text-based IFC well, while binary `.rvt` files grow a repository quickly.

## Share for review

**BIMDelta → Share for Review** sends the saved versions to GitHub and opens a pull request
for them, so a colleague can review the change before it reaches the main branch. With the
[GitHub Action](github-action.md) in the repository, the pull request gets the change summary
as a comment.

1. The first time, create an empty repository on GitHub (at
   [github.com/new](https://github.com/new), without a README) and paste its address into the
   dialog. The first Share publishes the history as the repository's `main` branch.
2. After that, save versions as usual, then **Share for Review**. On `main`, the dialog asks
   for a name for the change (suggested from the last version's message) and moves the new
   versions to a branch with that name; `main` goes back to what GitHub has, so it changes only
   when the pull request is merged.
3. The add-in pushes the branch and opens GitHub's pull request form in the browser. Add a
   title and choose **Create pull request**.
4. Versions saved after that go to the same branch; **Share for Review** again adds them to
   the same pull request.

**When someone else changed the model.** The `.rvt` file is not shared through Git: with
several people on one model, Revit worksharing (a central model, or Autodesk Docs) keeps it in
step, and **Synchronize with Central** before **Save Version** brings the others' changes into
the export. If `main` has model versions that your branch does not, for example because a
colleague's pull request was merged after you synchronised, Share stops before pushing and lists
them: the model you exported does not include them, so your pull request would undo them.
Update the model, save a new version and share again. **Share anyway** pushes regardless, for
when that is what you mean to do; the pull request comment then carries the same warning.

**Unsaved model.** Save Version exports the model that is open in Revit. If it has unsaved
changes, it offers to save the `.rvt` first, so the file and the version history hold the same
changes.

Sign-in is handled by Git Credential Manager, which comes with Git for Windows: the first push
opens a GitHub sign-in window, and Windows remembers it. The add-in does not store passwords
or tokens.

With a remote that is not on GitHub, Share pushes the branch and you open the merge request on
that host. Switching branches and merging are not done from Revit: the `.rvt` file is not
versioned, so checking out another branch would change the IFC but not the model.

## Undo a version

The last version can be taken back, keeping the files, with

```bash
git reset --soft HEAD~1
```

## Known limits

- **Unsigned add-in.** Revit asks once before loading it. Code signing is planned.
- **The export runs on Revit's main thread.** The Revit API cannot be used from another thread,
  so Revit is busy during the export; Revit shows its own progress. The change preview and the
  commit run in the background.
- **Reinforcement** modelled with Revit's rebar tools is exported as `IfcReinforcingBar`
  elements and diffed like any other element; reinforcement only described by parameters is
  not.
- **Viewer window.** It uses the WebView2 runtime that Revit ships. If it cannot be loaded, the
  viewer opens in the default browser instead.

## Build from source

```powershell
dotnet build revit\BIMDelta.Revit\BIMDelta.Revit.csproj -c Release -p:RevitVersion=2027
dotnet test revit\BIMDelta.Revit.Core.Tests
```

The project compiles against the Revit API reference packages, so no Revit installation is
needed to build. Output goes to `revit\BIMDelta.Revit\bin\Release\<version>\`.
