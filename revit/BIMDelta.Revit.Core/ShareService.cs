using System;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace BIMDelta.Revit.Core;

/// <summary>What Share will do, worked out without a network call.</summary>
public sealed class SharePlan
{
    public SharePlan(string branch, string baseBranch, string? remoteUrl, string suggestedName)
    {
        Branch = branch;
        BaseBranch = baseBranch;
        RemoteUrl = remoteUrl;
        SuggestedName = suggestedName;
    }

    public string Branch { get; }

    /// <summary>The repository's main branch, as far as is known locally.</summary>
    public string BaseBranch { get; }

    public string? RemoteUrl { get; }

    /// <summary>On the main branch, versions go to a new branch so they can be reviewed
    /// before they reach main.</summary>
    public bool NeedsBranchName => Branch == BaseBranch;

    public string SuggestedName { get; }
}

public enum ShareOutcome
{
    /// <summary>The remote was empty: the history was pushed as its main branch.</summary>
    Published,

    /// <summary>The branch was pushed and can be opened as a pull request.</summary>
    ReadyForReview,

    /// <summary>No version on this branch that the main branch does not have.</summary>
    NothingNew,
}

public sealed class ShareResult
{
    public ShareResult(ShareOutcome outcome, string branch, string? baseBranch, string? webUrl)
    {
        Outcome = outcome;
        Branch = branch;
        BaseBranch = baseBranch;
        WebUrl = webUrl;
    }

    public ShareOutcome Outcome { get; }
    public string Branch { get; }
    public string? BaseBranch { get; }

    /// <summary>The page to open: the new pull request form, or the repository. Null when the
    /// remote is not on GitHub.</summary>
    public string? WebUrl { get; }
}

/// <summary>Push the saved versions and open a pull request for them.</summary>
public sealed class ShareService
{
    public const string Remote = "origin";

    private readonly GitService _git;
    private readonly string _root;

    public ShareService(GitService git, string root)
    {
        _git = git;
        _root = root;
    }

    public SharePlan Plan()
    {
        var branch = _git.CurrentBranch(_root)
                     ?? throw new GitException("No branch is checked out. Check out a branch and try again.");
        var baseBranch = _git.KnownDefaultBranch(_root, Remote)
                         ?? (branch is "main" or "master" ? branch : "main");
        return new SharePlan(branch, baseBranch, _git.RemoteUrl(_root, Remote),
            SuggestBranchName(_git.LastCommitSubject(_root)));
    }

    /// <summary>Push the current branch. On the main branch, the versions not yet on the remote
    /// move to a new branch called <paramref name="newBranch"/> first, and main goes back to
    /// what the remote has, so the change reaches main only through a pull request.</summary>
    public ShareResult Share(string? newBranch)
    {
        if (!_git.HasCommits(_root))
            throw new GitException("There is no saved version yet. Use Save Version first.");
        var remoteUrl = _git.RemoteUrl(_root, Remote)
                        ?? throw new GitException("The project is not connected to a remote repository.");
        var branch = _git.CurrentBranch(_root)
                     ?? throw new GitException("No branch is checked out. Check out a branch and try again.");
        var web = GitHubRepository.Parse(remoteUrl);

        var baseBranch = _git.FetchDefaultBranch(_root, Remote);
        if (baseBranch == null)
        {
            _git.Push(_root, branch, Remote);
            return new ShareResult(ShareOutcome.Published, branch, null, web?.Url);
        }

        var remoteBase = $"{Remote}/{baseBranch}";
        if (_git.IsAncestor(_root, "HEAD", remoteBase))
            return new ShareResult(ShareOutcome.NothingNew, branch, baseBranch, web?.Url);

        if (branch == baseBranch)
        {
            var name = (newBranch ?? "").Trim();
            if (!_git.IsValidBranchName(_root, name))
                throw new ArgumentException($"\"{name}\" cannot be used as a branch name.");
            if (_git.BranchExists(_root, name))
                throw new ArgumentException($"A branch called \"{name}\" already exists.");
            _git.CreateBranch(_root, name);
            // Main was only ahead of the remote (versions saved on it): put it back, so it
            // matches the remote again and the new versions travel on the branch alone.
            if (_git.IsAncestor(_root, remoteBase, baseBranch))
                _git.MoveBranch(_root, baseBranch, remoteBase);
            branch = name;
        }

        _git.Push(_root, branch, Remote);
        return new ShareResult(ShareOutcome.ReadyForReview, branch, baseBranch,
            web?.CompareUrl(baseBranch, branch));
    }

    /// <summary>A branch name from a version's message: "Thicken L2 slab" → "thicken-l2-slab".</summary>
    public static string SuggestBranchName(string? text)
    {
        var folded = (text ?? "").Replace('ı', 'i').Replace('İ', 'I').Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (var c in folded)
        {
            if (CharUnicodeInfo.GetUnicodeCategory(c) == UnicodeCategory.NonSpacingMark) continue;
            var lower = char.ToLowerInvariant(c);
            if (lower is >= 'a' and <= 'z' or >= '0' and <= '9') sb.Append(lower);
            else if (sb.Length > 0 && sb[sb.Length - 1] != '-') sb.Append('-');
        }
        var name = sb.ToString().Trim('-');
        if (name.Length > 40) name = name.Substring(0, 40).TrimEnd('-');
        return name.Length == 0 ? "model-change" : name;
    }
}

/// <summary>A GitHub repository, from any of the URLs Git accepts for it.</summary>
public sealed class GitHubRepository
{
    private static readonly Regex Pattern = new(
        @"^(?:(?:https?|ssh)://(?:[^@/]+@)?|[^@/:]+@)github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$",
        RegexOptions.IgnoreCase);

    private GitHubRepository(string owner, string name)
    {
        Owner = owner;
        Name = name;
    }

    public string Owner { get; }
    public string Name { get; }
    public string Url => $"https://github.com/{Owner}/{Name}";

    public static GitHubRepository? Parse(string remoteUrl)
    {
        var match = Pattern.Match(remoteUrl.Trim());
        return match.Success ? new GitHubRepository(match.Groups[1].Value, match.Groups[2].Value) : null;
    }

    /// <summary>The "open a pull request" form for head into base.</summary>
    public string CompareUrl(string baseBranch, string head) =>
        $"{Url}/compare/{Escape(baseBranch)}...{Escape(head)}?expand=1";

    private static string Escape(string branch) =>
        string.Join("/", branch.Split('/').Select(Uri.EscapeDataString));
}
