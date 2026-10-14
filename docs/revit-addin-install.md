# Revit add-in

The add-in puts version history on the Revit ribbon: **Save Version** exports the model to IFC
and commits it to a Git repository next to the `.rvt` file; **Open Diff Viewer** shows the
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

If `bimdelta` is installed somewhere Revit's `PATH` does not reach (for example a virtual
environment), point the add-in to it:

```powershell
setx BIMDELTA_CLI "C:\path\to\venv\Scripts\bimdelta.exe"
```

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

To share the history, push the repository to GitHub or any Git host. With the
[GitHub Action](github-action.md), every pull request then gets the change summary as a comment.

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
