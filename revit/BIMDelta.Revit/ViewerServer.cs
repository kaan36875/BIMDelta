using System;
using System.Collections.Generic;
using System.Diagnostics;
using BIMDelta.Revit.Core;

namespace BIMDelta.Revit;

/// <summary>One `bimdelta serve` process per repository, kept while Revit runs.</summary>
public static class ViewerServer
{
    private static readonly Dictionary<string, (Process Process, string Url)> Servers =
        new(StringComparer.OrdinalIgnoreCase);

    public static string UrlFor(string root)
    {
        lock (Servers)
        {
            if (Servers.TryGetValue(root, out var running) && !running.Process.HasExited)
                return running.Url;
            var cli = BimDeltaCli.Find() ?? throw new BimDeltaNotFoundException();
            var started = cli.StartServer(root, TimeSpan.FromSeconds(30));
            Servers[root] = started;
            return started.Url;
        }
    }

    public static void StopAll()
    {
        lock (Servers)
        {
            foreach (var (process, _) in Servers.Values)
            {
                try
                {
                    if (!process.HasExited) process.Kill();
                }
                catch (InvalidOperationException)
                {
                }
                process.Dispose();
            }
            Servers.Clear();
        }
    }
}
