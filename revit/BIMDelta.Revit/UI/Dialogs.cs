using Autodesk.Revit.UI;

namespace BIMDelta.Revit.UI;

public enum UnsavedChoice
{
    SaveModel,
    VersionOnly,
    Cancel,
}

public static class Dialogs
{
    public static UnsavedChoice UnsavedModel(string title)
    {
        var dialog = new TaskDialog("BIMDelta")
        {
            MainIcon = TaskDialogIcon.TaskDialogIconWarning,
            MainInstruction = $"{title} has unsaved changes",
            MainContent = "The version is exported from the open model. Save the model too, so " +
                          "the .rvt file has the same changes as the version history.",
            CommonButtons = TaskDialogCommonButtons.Cancel,
        };
        dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Save the model, then the version");
        dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Save the version only",
            "The .rvt file stays as it is on disk.");
        return dialog.Show() switch
        {
            TaskDialogResult.CommandLink1 => UnsavedChoice.SaveModel,
            TaskDialogResult.CommandLink2 => UnsavedChoice.VersionOnly,
            _ => UnsavedChoice.Cancel,
        };
    }

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
