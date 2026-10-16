using System;
using System.Linq;
using System.IO;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using BIMDelta.Revit.Core;
using BIMDelta.Revit.UI;

namespace BIMDelta.Revit.Commands;

/// <summary>Export the model to ifc/&lt;project&gt;.ifc, preview the changes and commit them.</summary>
[Transaction(TransactionMode.Manual)]
public sealed class SaveVersionCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var uiapp = commandData.Application;
        var doc = uiapp.ActiveUIDocument?.Document;
        if (doc == null || doc.IsFamilyDocument)
        {
            Dialogs.Error("Open a project to save a version of it.");
            return Result.Cancelled;
        }
        if (string.IsNullOrEmpty(doc.PathName) || !File.Exists(doc.PathName))
        {
            Dialogs.Error("Save the project first: versions are kept in a Git repository next to " +
                          "the .rvt file.");
            return Result.Cancelled;
        }

        var git = GitService.Find();
        if (git == null)
        {
            Dialogs.Error("Git is not installed.",
                "Install Git for Windows from https://git-scm.com/download/win, then restart Revit.");
            return Result.Failed;
        }

        // The version is exported from the open model; if the .rvt is never saved, the history
        // holds changes the model file does not.
        if (doc.IsModified)
        {
            switch (Dialogs.UnsavedModel(doc.Title))
            {
                case UnsavedChoice.Cancel:
                    return Result.Cancelled;
                case UnsavedChoice.SaveModel:
                    try
                    {
                        doc.Save();
                    }
                    catch (Exception e)
                    {
                        Dialogs.Error("The model could not be saved.", e.Message);
                        return Result.Failed;
                    }
                    break;
            }
        }

        var modelFolder = Path.GetDirectoryName(doc.PathName)!;
        var root = git.FindRepositoryRoot(modelFolder);
        if (root == null)
        {
            var lfs = git.HasLfs(modelFolder);
            if (!Dialogs.Confirm("Start version history for this project?",
                    $"A Git repository will be created in\n{modelFolder}\n\n" +
                    "The IFC export is versioned in an ifc folder there; the .rvt file is not." +
                    (lfs ? "" : "\n\nGit LFS is not installed, so IFC files are stored as plain " +
                                "Git files. That is fine below about 50 MB.")))
                return Result.Cancelled;
            try
            {
                git.Initialise(modelFolder, lfs);
            }
            catch (GitException e)
            {
                Dialogs.Error("Could not create the repository.", e.Message);
                return Result.Failed;
            }
            root = modelFolder;
        }

        var cli = BimDeltaCli.Find();
        if (cli != null)
        {
            try
            {
                cli.InstallGitDriver(root);
            }
            catch (Exception)
            {
                // git diff stays plain text; versions still work.
            }
        }

        var ifcPath = VersionLayout.IfcPath(root, doc.Title);
        try
        {
            IfcExportService.Export(doc, ifcPath);
        }
        catch (Exception e)
        {
            Dialogs.Error("The IFC export failed.", e.Message);
            return Result.Failed;
        }

        var relative = GitService.RelativePath(root, ifcPath);
        var dialog = new CommitDialog(git, cli, root, relative, uiapp.MainWindowHandle);
        if (dialog.ShowDialog() != true) return Result.Cancelled;

        var author = string.IsNullOrWhiteSpace(uiapp.Application.Username)
            ? Environment.UserName
            : uiapp.Application.Username;
        var email = git.ConfiguredEmail(root) ?? $"{Environment.UserName}@users.noreply.local";
        string? sha;
        try
        {
            sha = git.Commit(root, new[] { relative, ".gitattributes", ".gitignore" }
                    .Where(p => File.Exists(Path.Combine(root, p))),
                dialog.Message, author, email);
        }
        catch (GitException e)
        {
            Dialogs.Error("The commit failed.", e.Message);
            return Result.Failed;
        }

        if (sha == null)
        {
            Dialogs.Info("Nothing to save", "The model is the same as in the last saved version.");
            return Result.Succeeded;
        }
        if (Dialogs.Saved(sha.Substring(0, 7), relative))
            OpenViewerCommand.Open(uiapp, root);
        return Result.Succeeded;
    }
}
