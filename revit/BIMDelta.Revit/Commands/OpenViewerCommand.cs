using System;
using System.Diagnostics;
using System.IO;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using BIMDelta.Revit.Core;
using BIMDelta.Revit.UI;

namespace BIMDelta.Revit.Commands;

/// <summary>Open the project's version history in the viewer (bimdelta serve).</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class OpenViewerCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var uiapp = commandData.Application;
        var doc = uiapp.ActiveUIDocument?.Document;
        if (doc == null || string.IsNullOrEmpty(doc.PathName))
        {
            Dialogs.Error("Open a saved project to see its versions.");
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
        if (root == null)
        {
            Dialogs.Info("No versions yet", "Use Save Version to start the project's history.");
            return Result.Cancelled;
        }
        return Open(uiapp, root) ? Result.Succeeded : Result.Failed;
    }

    public static bool Open(UIApplication uiapp, string root)
    {
        string url;
        try
        {
            url = ViewerServer.UrlFor(root);
        }
        catch (BimDeltaNotFoundException e)
        {
            Dialogs.Error("The viewer needs the bimdelta command line tool.",
                e.Message + "\n\nIt needs Python 3.10 or newer: https://www.python.org/downloads/");
            return false;
        }
        catch (Exception e)
        {
            Dialogs.Error("The viewer could not start.", e.Message);
            return false;
        }

        if (!ViewerWindow.TryShow(url, Path.GetFileName(root), uiapp.MainWindowHandle))
        {
            // No WebView2 in this Revit: the default browser does the same job.
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        return true;
    }
}
