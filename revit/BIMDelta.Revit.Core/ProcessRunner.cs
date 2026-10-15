using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;

namespace BIMDelta.Revit.Core;

public sealed class ProcessResult
{
    public ProcessResult(int exitCode, string stdout, string stderr)
    {
        ExitCode = exitCode;
        Stdout = stdout;
        Stderr = stderr;
    }

    public int ExitCode { get; }
    public string Stdout { get; }
    public string Stderr { get; }
    public bool Ok => ExitCode == 0;

    /// <summary>The most useful line of output for an error message.</summary>
    public string Message
    {
        get
        {
            var text = string.IsNullOrWhiteSpace(Stderr) ? Stdout : Stderr;
            return text.Trim();
        }
    }
}

/// <summary>A command line program and the arguments that always come first, e.g. "py -m x".</summary>
public sealed class Command
{
    public Command(string executable, params string[] prefix)
    {
        Executable = executable;
        Prefix = prefix;
    }

    public string Executable { get; }
    public IReadOnlyList<string> Prefix { get; }

    public override string ToString() =>
        string.Join(" ", new[] { Executable }.Concat(Prefix).Select(ProcessRunner.Quote));
}

public static class ProcessRunner
{
    public static ProcessResult Run(Command command, IEnumerable<string> args, string workingDirectory,
        TimeSpan? timeout = null)
    {
        using var process = Start(command, args, workingDirectory);
        // Read both streams at once so a full stderr buffer cannot block the child.
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit((int)(timeout ?? TimeSpan.FromMinutes(10)).TotalMilliseconds))
        {
            TryKill(process);
            throw new TimeoutException($"{command} did not finish in time");
        }
        process.WaitForExit();
        return new ProcessResult(process.ExitCode, stdout.Result, stderr.Result);
    }

    /// <summary>Run a command and write its standard output, unchanged, to a file.</summary>
    public static ProcessResult RunToFile(Command command, IEnumerable<string> args,
        string workingDirectory, string outputPath)
    {
        using var process = Start(command, args, workingDirectory);
        var stderr = process.StandardError.ReadToEndAsync();
        using (var file = File.Create(outputPath))
        {
            process.StandardOutput.BaseStream.CopyTo(file);
        }
        process.WaitForExit();
        return new ProcessResult(process.ExitCode, "", stderr.Result);
    }

    public static Process Start(Command command, IEnumerable<string> args, string workingDirectory)
    {
        var all = command.Prefix.Concat(args);
        var info = new ProcessStartInfo(command.Executable, string.Join(" ", all.Select(Quote)))
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        // bimdelta prints → and ∅; make sure Python writes UTF-8 to the pipe.
        info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        info.EnvironmentVariables["PYTHONUTF8"] = "1";
        // There is no console to type a password into; Git Credential Manager shows its own
        // sign-in window instead, and anything else fails rather than waiting forever.
        info.EnvironmentVariables["GIT_TERMINAL_PROMPT"] = "0";
        return Process.Start(info) ?? throw new InvalidOperationException($"could not start {command}");
    }

    /// <summary>Quote one argument the way the Windows C runtime parses command lines.</summary>
    public static string Quote(string arg)
    {
        if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
            return arg;
        var sb = new StringBuilder("\"");
        var backslashes = 0;
        foreach (var c in arg)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }
            if (c == '"')
            {
                sb.Append('\\', backslashes * 2 + 1);
            }
            else
            {
                sb.Append('\\', backslashes);
            }
            backslashes = 0;
            sb.Append(c);
        }
        sb.Append('\\', backslashes * 2);
        sb.Append('"');
        return sb.ToString();
    }

    public static string? FindOnPath(string name)
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        var extensions = (Environment.GetEnvironmentVariable("PATHEXT") ?? ".EXE;.CMD;.BAT")
            .Split(';').Where(e => e.Length > 0).ToArray();
        foreach (var dir in path.Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(dir)) continue;
            foreach (var candidate in new[] { name }.Concat(extensions.Select(e => name + e)))
            {
                try
                {
                    var full = Path.Combine(dir.Trim(), candidate);
                    if (File.Exists(full)) return full;
                }
                catch (ArgumentException)
                {
                    // malformed PATH entry
                }
            }
        }
        return null;
    }

    private static void TryKill(Process process)
    {
        try
        {
            process.Kill();
        }
        catch (InvalidOperationException)
        {
        }
    }
}
