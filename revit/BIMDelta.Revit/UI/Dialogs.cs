using Autodesk.Revit.UI;

namespace BIMDelta.Revit.UI;

public static class Dialogs
{
    public static void Error(string title, string? detail = null)
    {
        var dialog = new TaskDialog("BIMDelta")
        {
            MainIcon = TaskDialogIcon.TaskDialogIconError,
            MainInstruction = title,
            MainContent = detail ?? "",
        };
        dialog.Show();
    }

    public static void Info(string title, string detail)
    {
        new TaskDialog("BIMDelta") { MainInstruction = title, MainContent = detail }.Show();
    }

    public static bool Confirm(string title, string detail)
    {
        var dialog = new TaskDialog("BIMDelta")
        {
            MainInstruction = title,
            MainContent = detail,
            CommonButtons = TaskDialogCommonButtons.Ok | TaskDialogCommonButtons.Cancel,
            DefaultButton = TaskDialogResult.Ok,
        };
        return dialog.Show() == TaskDialogResult.Ok;
    }

    /// <summary>Report a saved version; true if the user wants to see it in the viewer.</summary>
    public static bool Saved(string shortSha, string path)
    {
        var dialog = new TaskDialog("BIMDelta")
        {
            MainInstruction = $"Version saved as {shortSha}",
            MainContent = $"Committed {path}.",
        };
        dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "View changes",
            "Open the version history in the diff viewer.");
        dialog.CommonButtons = TaskDialogCommonButtons.Close;
        return dialog.Show() == TaskDialogResult.CommandLink1;
    }
}
