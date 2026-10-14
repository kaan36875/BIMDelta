using System.IO;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using BIMDelta.Revit.Core;
using BIMDelta.Revit.UI;

namespace BIMDelta.Revit.Commands;

/// <summary>Push the saved versions and open the pull request form for them.</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class ShareCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var uiapp = commandData.Application;
        var doc = uiapp.ActiveUIDocument?.Document;
        if (doc == null || string.IsNullOrEmpty(doc.PathName))
        {
            Dialogs.Error("Open a saved project to share its versions.");
            return Result.Cancelled;
        }
        var git = GitService.Find();
        if (git == null)
        {
            Dialogs.Error("Git is not installed.",
                "Install Git for Windows from https://git-scm.com/download/win, then restart Revit.");
            return Result.Failed;
        }
        var root = git.FindRepositoryRoot(Path.GetDirectoryName(doc.PathName)!);
        if (root == null || !git.HasCommits(root))
        {
            Dialogs.Info("No versions yet", "Use Save Version first; Share sends the saved versions.");
            return Result.Cancelled;
        }

        SharePlan plan;
        try
        {
            plan = new ShareService(git, root).Plan();
        }
        catch (GitException e)
        {
            Dialogs.Error("Cannot share from this repository.", e.Message);
            return Result.Failed;
        }

        var dialog = new ShareDialog(git, root, plan, uiapp.MainWindowHandle);
        if (dialog.ShowDialog() != true || dialog.Result == null) return Result.Cancelled;

        var result = dialog.Result;
        if (result.WebUrl != null) ShareDialog.OpenInBrowser(result.WebUrl);
        if (result.Outcome == ShareOutcome.Published)
        {
            Dialogs.Info("History published",
                $"The saved versions are now the repository's {result.Branch} branch. From here on, " +
                "Share sends new versions on a branch of their own, for review in a pull request.");
        }
        else
        {
            Dialogs.Info($"Shared on {result.Branch}",
                (result.WebUrl != null
                    ? "Your browser shows the pull request form: add a title and choose Create pull request."
                    : $"Open a pull request from {result.Branch} into {result.BaseBranch} on your Git host.") +
                $"\n\nVersions you save from now on go to {result.Branch}; Share again to add them " +
                "to the same pull request.");
        }
        return Result.Succeeded;
    }
}
