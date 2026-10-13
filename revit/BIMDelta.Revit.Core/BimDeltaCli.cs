using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace BIMDelta.Revit.Core;

/// <summary>Counts from `bimdelta diff --format json --summary-only`.</summary>
public sealed class ChangeSummary
{
    public int Added { get; set; }
    public int Removed { get; set; }
    public int Modified { get; set; }
    public int Unchanged { get; set; }
    public Dictionary<string, Dictionary<string, int>> ByClass { get; set; } = new();

    public bool HasChanges => Added + Removed + Modified > 0;

    public static ChangeSummary Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        var summary = new ChangeSummary
        {
            Added = root.GetProperty("added").GetInt32(),
            Removed = root.GetProperty("removed").GetInt32(),
            Modified = root.GetProperty("modified").GetInt32(),
            Unchanged = root.GetProperty("unchanged").GetInt32(),
        };
        if (root.TryGetProperty("by_class", out var byClass))
        {
            foreach (var cls in byClass.EnumerateObject())
            {
                summary.ByClass[cls.Name] = cls.Value.EnumerateObject()
                    .ToDictionary(p => p.Name, p => p.Value.GetInt32());
            }
        }
        return summary;
    }

    /// <summary>"3 added · 1 removed · 12 modified", then one line per changed class.</summary>
    public string Describe()
    {
        if (!HasChanges) return $"No element changes ({Unchanged} unchanged).";
        var lines = new List<string> { $"{Added} added · {Removed} removed · {Modified} modified" };
        foreach (var kv in ByClass.OrderBy(kv => kv.Key, StringComparer.Ordinal))
        {
            int Get(string k) => kv.Value.TryGetValue(k, out var n) ? n : 0;
            if (Get("added") + Get("removed") + Get("modified") == 0) continue;
            var parts = new[] { ("added", "+"), ("removed", "−"), ("modified", "~") }
                .Where(p => Get(p.Item1) > 0)
                .Select(p => $"{p.Item2}{Get(p.Item1)}");
            lines.Add($"  {kv.Key}: {string.Join(" ", parts)}");
        }
        return string.Join(Environment.NewLine, lines);
    }
}

public sealed class BimDeltaNotFoundException : Exception
{
    public BimDeltaNotFoundException() : base(
        "The bimdelta command was not found. Install it with: pip install bimdelta")
    {
    }
}

/// <summary>The bimdelta command line program.</summary>
public sealed class BimDeltaCli
{
    private readonly Command _command;

    public BimDeltaCli(Command command)
    {
        _command = command;
    }

    public override string ToString() => _command.ToString();

    /// <summary>bimdelta on PATH, in a per-user Python Scripts folder, or through the py launcher.</summary>
    public static BimDeltaCli? Find()
    {
        var exe = ProcessRunner.FindOnPath("bimdelta");
        if (exe != null) return new BimDeltaCli(new Command(exe));

        var roaming = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var candidates = new[] { Path.Combine(roaming, "Python"), Path.Combine(local, "Programs", "Python") }
            .Where(Directory.Exists)
            .SelectMany(d => Directory.GetDirectories(d, "Python3*"))
            .OrderByDescending(d => d, StringComparer.OrdinalIgnoreCase)
            .Select(d => Path.Combine(d, "Scripts", "bimdelta.exe"))
            .Where(File.Exists);
        var found = candidates.FirstOrDefault();
        if (found != null) return new BimDeltaCli(new Command(found));

        var py = ProcessRunner.FindOnPath("py");
        if (py != null)
        {
            var cli = new BimDeltaCli(new Command(py, "-m", "bimdelta_cli"));
            if (cli.Version() != null) return cli;
        }
        return null;
    }

    public string? Version()
    {
        try
        {
            var result = ProcessRunner.Run(_command, new[] { "--version" }, Path.GetTempPath(),
                TimeSpan.FromSeconds(30));
            return result.Ok ? result.Stdout.Trim() : null;
        }
        catch (Exception)
        {
            return null;
        }
    }

    public ChangeSummary Diff(string oldIfc, string newIfc, string workingDirectory)
    {
        var result = ProcessRunner.Run(_command,
            new[] { "diff", oldIfc, newIfc, "--format", "json", "--summary-only" }, workingDirectory);
        if (!result.Ok) throw new InvalidOperationException(result.Message);
        return ChangeSummary.Parse(result.Stdout);
    }

    public void InstallGitDriver(string root)
    {
        var result = ProcessRunner.Run(_command, new[] { "install-git-driver" }, root);
        if (!result.Ok) throw new InvalidOperationException(result.Message);
    }

    /// <summary>Start `bimdelta serve` for a repository and wait for the URL it prints.</summary>
    public (Process Process, string Url) StartServer(string root, TimeSpan timeout)
    {
        var process = ProcessRunner.Start(_command, new[] { "serve", "--repo", root, "--no-open" }, root);
        var line = process.StandardOutput.ReadLineAsync();
        if (!line.Wait(timeout) || line.Result == null || !line.Result.StartsWith("BIMDELTA_URL="))
        {
            var error = process.HasExited ? process.StandardError.ReadToEnd().Trim() : "no response";
            try
            {
                if (!process.HasExited) process.Kill();
            }
            catch (InvalidOperationException)
            {
            }
            throw new InvalidOperationException($"bimdelta serve did not start: {error}");
        }
        // Keep draining output so the pipe never fills up.
        process.ErrorDataReceived += (_, _) => { };
        process.BeginErrorReadLine();
        _ = process.StandardOutput.ReadToEndAsync();
        return (process, line.Result.Substring("BIMDELTA_URL=".Length).Trim());
    }
}
