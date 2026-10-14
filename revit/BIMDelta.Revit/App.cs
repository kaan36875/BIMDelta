using System;
using System.IO;
using System.Reflection;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;
using BIMDelta.Revit.Commands;

namespace BIMDelta.Revit;

/// <summary>Adds the BIMDelta ribbon tab.</summary>
public sealed class App : IExternalApplication
{
    public const string TabName = "BIMDelta";

    public Result OnStartup(UIControlledApplication application)
    {
        try
        {
            application.CreateRibbonTab(TabName);
        }
        catch (Autodesk.Revit.Exceptions.ArgumentException)
        {
            // Tab already exists.
        }
        var panel = application.CreateRibbonPanel(TabName, "Versions");
        var assembly = Assembly.GetExecutingAssembly().Location;

        var save = new PushButtonData("BIMDeltaSaveVersion", "Save\nVersion", assembly,
            typeof(SaveVersionCommand).FullName)
        {
            ToolTip = "Export the model to IFC and commit it to the project's Git repository.",
            LongDescription = "Writes ifc/<project>.ifc next to the model with fixed export " +
                              "settings, shows what changed since the last version and commits it.",
            LargeImage = Icon("save-32.png"),
            Image = Icon("save-16.png"),
        };
        var viewer = new PushButtonData("BIMDeltaOpenViewer", "Open Diff\nViewer", assembly,
            typeof(OpenViewerCommand).FullName)
        {
            ToolTip = "Browse the saved versions: timeline, 3D diff and element history.",
            LargeImage = Icon("viewer-32.png"),
            Image = Icon("viewer-16.png"),
        };
        panel.AddItem(save);
        panel.AddItem(viewer);
        return Result.Succeeded;
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        ViewerServer.StopAll();
        return Result.Succeeded;
    }

    private static BitmapImage? Icon(string name)
    {
        var stream = Assembly.GetExecutingAssembly()
            .GetManifestResourceStream($"BIMDelta.Revit.Resources.{name}");
        if (stream == null) return null;
        var image = new BitmapImage();
        image.BeginInit();
        image.StreamSource = stream;
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.EndInit();
        image.Freeze();
        return image;
    }

    /// <summary>Folder for logs and WebView2 data.</summary>
    public static string DataFolder
    {
        get
        {
            var path = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BIMDelta");
            Directory.CreateDirectory(path);
            return path;
        }
    }
}
