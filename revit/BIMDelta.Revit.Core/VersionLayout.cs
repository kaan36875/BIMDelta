using System.IO;
using System.Linq;

namespace BIMDelta.Revit.Core;

/// <summary>Where a Revit project's versions live: an ifc/ folder in the repository holding
/// the model, one IFC file per Revit project.</summary>
public static class VersionLayout
{
    public const string IfcFolder = "ifc";

    public static string IfcPath(string repositoryRoot, string projectTitle) =>
        Path.Combine(repositoryRoot, IfcFolder, FileName(projectTitle));

    /// <summary>A file name from a Revit document title ("Tower.rvt", "Tower - A.rvt").</summary>
    public static string FileName(string projectTitle)
    {
        var title = projectTitle;
        if (title.EndsWith(".rvt", System.StringComparison.OrdinalIgnoreCase))
            title = title.Substring(0, title.Length - 4);
        var invalid = Path.GetInvalidFileNameChars();
        var clean = new string(title.Select(c => invalid.Contains(c) ? '_' : c).ToArray()).Trim(' ', '.');
        return (clean.Length == 0 ? "model" : clean) + ".ifc";
    }
}
