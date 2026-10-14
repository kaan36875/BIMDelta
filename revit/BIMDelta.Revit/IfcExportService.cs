using System;
using System.IO;
using Autodesk.Revit.DB;

namespace BIMDelta.Revit;

/// <summary>IFC export with settings fixed for every version, so consecutive exports differ
/// only where the model does.</summary>
public static class IfcExportService
{
    public static void Export(Document doc, string ifcPath)
    {
        var folder = Path.GetDirectoryName(ifcPath)!;
        Directory.CreateDirectory(folder);
        var name = Path.GetFileNameWithoutExtension(ifcPath);

        var options = new IFCExportOptions
        {
            FileVersion = IFCVersion.IFC4RV,
            WallAndColumnSplitting = false,
            ExportBaseQuantities = true,
        };
        // Options read by Revit's open-source IFC exporter.
        options.AddOption("ExportIFCCommonPropertySets", "true");
        options.AddOption("ExportInternalRevitPropertySets", "false");
        options.AddOption("ExportBaseQuantities", "true");
        options.AddOption("ExportSchedulesAsPsets", "false");
        options.AddOption("ExportPartsAsBuildingElements", "false");
        options.AddOption("VisibleElementsOfCurrentView", "false");
        options.AddOption("SpaceBoundaries", "0");
        options.AddOption("IncludeSiteElevation", "true");
        // Keep the model unchanged: GUIDs are derived from element ids either way.
        options.AddOption("StoreIFCGUID", "false");

        // Export into a scratch folder first, so a failed export never leaves half a file
        // where the last version was.
        var scratch = Path.Combine(Path.GetTempPath(), "bimdelta-export-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(scratch);
        try
        {
            // The exporter needs an open transaction; rolling it back leaves the model as it was.
            using (var tx = new Transaction(doc, "BIMDelta IFC export"))
            {
                tx.Start();
                var ok = doc.Export(scratch, name + ".ifc", options);
                tx.RollBack();
                if (!ok) throw new InvalidOperationException("Revit's IFC export reported a failure.");
            }
            var produced = Directory.GetFiles(scratch, "*.ifc");
            if (produced.Length == 0)
                throw new InvalidOperationException("Revit's IFC export did not produce a file.");
            if (File.Exists(ifcPath)) File.Delete(ifcPath);
            File.Move(produced[0], ifcPath);
        }
        finally
        {
            try
            {
                Directory.Delete(scratch, true);
            }
            catch (IOException)
            {
            }
        }
    }
}
