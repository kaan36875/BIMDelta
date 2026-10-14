using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace BIMDelta.Revit.Core;

public sealed class GitException : Exception
{
    public GitException(string message) : base(message)
    {
    }
}

/// <summary>Git through git.exe. LibGit2Sharp is not used: it does not run Git LFS filters.</summary>
public sealed class GitService
{
    public const string AttributesLine = "*.ifc diff=ifc";
    public const string LfsAttributesLine = "*.ifc filter=lfs diff=ifc merge=lfs -text";

    // The Revit model stays where it is; the IFC export is what gets versioned.
    public static readonly string[] IgnoreLines =
    {
        "# Revit models and backups: versioned as IFC exports in ifc/",
        "*.rvt",
        "*.rfa",
        "*_backup/",
        "*.ifc.tmp",
    };

    private readonly Command _git;

    public GitService(Command git)
    {
        _git = git;
    }

    public static GitService? Find()
    {
        var exe = ProcessRunner.FindOnPath("git");
        if (exe == null)
        {
            foreach (var root in new[]
                     {
                         Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                         Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + @"\Programs",
                     })
            {
                var candidate = Path.Combine(root, "Git", "cmd", "git.exe");
                if (File.Exists(candidate))
                {
                    exe = candidate;
                    break;
                }
            }
        }
        return exe == null ? null : new GitService(new Command(exe));
    }

    public ProcessResult Run(string cwd, params string[] args) => ProcessRunner.Run(_git, args, cwd);

    private string Check(string cwd, params string[] args)
    {
        var result = Run(cwd, args);
        if (!result.Ok) throw new GitException($"git {args.FirstOrDefault()}: {result.Message}");
        return result.Stdout.Trim();
    }

    public string? FindRepositoryRoot(string directory)
    {
        if (!Directory.Exists(directory)) return null;
        var result = Run(directory, "rev-parse", "--show-toplevel");
        return result.Ok ? Path.GetFullPath(result.Stdout.Trim()) : null;
    }

    public bool HasLfs(string cwd) => Run(cwd, "lfs", "version").Ok;

    /// <summary>Create a repository with the attributes and ignore rules BIMDelta needs.</summary>
    public void Initialise(string directory, bool useLfs)
    {
        // main, as GitHub names a new repository's branch, whatever init.defaultBranch says.
        Check(directory, "init", "--initial-branch=main");
        if (useLfs) Check(directory, "lfs", "install", "--local");
        EnsureAttributes(directory, useLfs);
        EnsureLines(Path.Combine(directory, ".gitignore"), IgnoreLines);
    }

    /// <summary>Map *.ifc to the BIMDelta diff driver, unless the repository already maps it.</summary>
    public static bool EnsureAttributes(string root, bool useLfs)
    {
        var path = Path.Combine(root, ".gitattributes");
        var lines = File.Exists(path) ? File.ReadAllLines(path).ToList() : new List<string>();
        if (lines.Any(l => l.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries)
                .FirstOrDefault() == "*.ifc"))
            return false;
        lines.Add(useLfs ? LfsAttributesLine : AttributesLine);
        File.WriteAllText(path, string.Join("\n", lines) + "\n");
        return true;
    }

    public static bool EnsureLines(string path, IEnumerable<string> wanted)
    {
        var lines = File.Exists(path) ? File.ReadAllLines(path).ToList() : new List<string>();
        var missing = wanted.Where(w => !lines.Contains(w)).ToList();
        if (missing.Count == 0) return false;
        lines.AddRange(missing);
        File.WriteAllText(path, string.Join("\n", lines) + "\n");
        return true;
    }

    /// <summary>Repository-relative path with forward slashes, as Git prints it.</summary>
    public static string RelativePath(string root, string file)
    {
        var rootFull = Path.GetFullPath(root).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
        var fileFull = Path.GetFullPath(file);
        if (!fileFull.StartsWith(rootFull, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException($"{file} is not inside {root}");
        return fileFull.Substring(rootFull.Length).Replace('\\', '/');
    }

    /// <summary>Write the committed version of a file (LFS content resolved) to dest.
    /// Returns false if HEAD does not have the file.</summary>
    public bool WriteHeadVersion(string root, string relativePath, string dest)
    {
        if (!Run(root, "cat-file", "-e", $"HEAD:{relativePath}").Ok) return false;
        var result = ProcessRunner.RunToFile(_git, new[] { "cat-file", "--filters", $"HEAD:{relativePath}" },
            root, dest);
        if (!result.Ok) throw new GitException($"git cat-file: {result.Message}");
        return true;
    }

    public string? ConfiguredEmail(string root)
    {
        var result = Run(root, "config", "user.email");
        return result.Ok && result.Stdout.Trim().Length > 0 ? result.Stdout.Trim() : null;
    }

    /// <summary>Stage the files and commit them. Returns the new commit's id, or null when
    /// nothing changed since the last commit.</summary>
    public string? Commit(string root, IEnumerable<string> relativePaths, string message,
        string authorName, string authorEmail)
    {
        var paths = relativePaths.ToArray();
        Check(root, new[] { "add", "--" }.Concat(paths).ToArray());
        if (Run(root, "diff", "--cached", "--quiet").Ok) return null;

        Check(root,
            "-c", $"user.name={authorName}",
            "-c", $"user.email={authorEmail}",
            "commit", "--quiet", "-m", message);
        return Check(root, "rev-parse", "HEAD");
    }

    public bool HasCommits(string root) => Run(root, "rev-parse", "--verify", "--quiet", "HEAD").Ok;

    /// <summary>The checked-out branch, or null on a detached HEAD.</summary>
    public string? CurrentBranch(string root)
    {
        var result = Run(root, "symbolic-ref", "--quiet", "--short", "HEAD");
        return result.Ok ? result.Stdout.Trim() : null;
    }

    public string? LastCommitSubject(string root)
    {
        var result = Run(root, "log", "-1", "--format=%s");
        return result.Ok ? result.Stdout.Trim() : null;
    }

    public string? RemoteUrl(string root, string remote = "origin")
    {
        var result = Run(root, "remote", "get-url", remote);
        return result.Ok && result.Stdout.Trim().Length > 0 ? result.Stdout.Trim() : null;
    }

    public void AddRemote(string root, string url, string remote = "origin") =>
        Check(root, "remote", "add", remote, url);

    /// <summary>The remote's default branch as last fetched (origin/HEAD), without a network call.</summary>
    public string? KnownDefaultBranch(string root, string remote = "origin")
    {
        var result = Run(root, "symbolic-ref", "--quiet", "--short", $"refs/remotes/{remote}/HEAD");
        if (!result.Ok) return null;
        var name = result.Stdout.Trim();
        return name.StartsWith(remote + "/") ? name.Substring(remote.Length + 1) : name;
    }

    /// <summary>Fetch and ask the remote for its default branch. Null when the remote has no
    /// branches yet (a new, empty repository).</summary>
    public string? FetchDefaultBranch(string root, string remote = "origin")
    {
        Check(root, "fetch", "--quiet", remote);
        if (!Run(root, "remote", "set-head", remote, "--auto").Ok) return null;
        return KnownDefaultBranch(root, remote);
    }

    public bool IsValidBranchName(string root, string name) =>
        name.Length > 0 && Run(root, "check-ref-format", "--branch", name).Ok;

    public bool BranchExists(string root, string name) =>
        Run(root, "rev-parse", "--verify", "--quiet", $"refs/heads/{name}").Ok;

    /// <summary>Start a branch at HEAD and switch to it. The working tree does not change.</summary>
    public void CreateBranch(string root, string name) => Check(root, "checkout", "--quiet", "-b", name);

    /// <summary>Point a branch that is not checked out at another commit.</summary>
    public void MoveBranch(string root, string name, string target) =>
        Check(root, "branch", "--force", name, target);

    public bool IsAncestor(string root, string ancestor, string descendant) =>
        Run(root, "merge-base", "--is-ancestor", ancestor, descendant).Ok;

    public void Push(string root, string branch, string remote = "origin") =>
        Check(root, "push", "--quiet", "--set-upstream", remote, branch);
}
