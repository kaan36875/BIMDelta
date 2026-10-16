using System;
using System.IO;
using BIMDelta.Revit.Core;
using Xunit;

namespace BIMDelta.Revit.Core.Tests;

public sealed class TempRepo : IDisposable
{
    public TempRepo()
    {
        Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "bimdelta-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path);
    }

    public string Path { get; }

    public void Dispose()
    {
        try
        {
            foreach (var f in Directory.GetFiles(Path, "*", SearchOption.AllDirectories))
                File.SetAttributes(f, FileAttributes.Normal); // .git objects are read-only
            Directory.Delete(Path, true);
        }
        catch (IOException)
        {
        }
    }
}

public class ProcessRunnerTests
{
    [Theory]
    [InlineData("plain", "plain")]
    [InlineData("two words", "\"two words\"")]
    [InlineData("", "\"\"")]
    [InlineData("say \"hi\"", "\"say \\\"hi\\\"\"")]
    [InlineData(@"C:\dir with space\", "\"C:\\dir with space\\\\\"")]
    [InlineData("user.name=Ayşe Yılmaz", "\"user.name=Ayşe Yılmaz\"")]
    public void QuotesLikeTheWindowsRuntime(string arg, string expected)
    {
        Assert.Equal(expected, ProcessRunner.Quote(arg));
    }
}

public class VersionLayoutTests
{
    [Theory]
    [InlineData("Tower.rvt", "Tower.ifc")]
    [InlineData("Tower - Option A", "Tower - Option A.ifc")]
    [InlineData("a/b:c*?.rvt", "a_b_c__.ifc")]
    [InlineData(".rvt", "model.ifc")]
    public void FileNameFromTitle(string title, string expected)
    {
        Assert.Equal(expected, VersionLayout.FileName(title));
    }

    [Fact]
    public void IfcPathIsInTheIfcFolder()
    {
        var path = VersionLayout.IfcPath(@"C:\proj", "Tower.rvt");
        Assert.Equal(Path.Combine(@"C:\proj", "ifc", "Tower.ifc"), path);
        Assert.Equal("ifc/Tower.ifc", GitService.RelativePath(@"C:\proj", path));
    }
}

public class ChangeSummaryTests
{
    private const string Json = """
        {"total_v1": 10, "total_v2": 11, "added": 2, "removed": 1, "modified": 3, "unchanged": 5,
         "by_class": {"IfcWall": {"modified": 3, "unchanged": 4},
                      "IfcDoor": {"added": 2, "removed": 1},
                      "IfcSlab": {"unchanged": 1}},
         "by_storey": {}}
        """;

    [Fact]
    public void ParsesCounts()
    {
        var s = ChangeSummary.Parse(Json);
        Assert.Equal((2, 1, 3, 5), (s.Added, s.Removed, s.Modified, s.Unchanged));
        Assert.True(s.HasChanges);
        Assert.Equal(4, s.ByClass["IfcWall"]["unchanged"]);
    }

    [Fact]
    public void DescribesChangedClassesOnly()
    {
        var text = ChangeSummary.Parse(Json).Describe();
        Assert.StartsWith("2 added · 1 removed · 3 modified", text);
        Assert.Contains("IfcDoor: +2 −1", text);
        Assert.Contains("IfcWall: ~3", text);
        Assert.DoesNotContain("IfcSlab", text);
    }

    [Fact]
    public void DescribesNoChanges()
    {
        var s = ChangeSummary.Parse("""{"added":0,"removed":0,"modified":0,"unchanged":7}""");
        Assert.Equal("No element changes (7 unchanged).", s.Describe());
    }
}

public class GitServiceTests
{
    private static GitService Git => GitService.Find() ?? throw new InvalidOperationException("git not found");

    [Fact]
    public void InitialiseWritesAttributesAndIgnores()
    {
        using var repo = new TempRepo();
        Git.Initialise(repo.Path, useLfs: false);

        Assert.Equal(Path.GetFullPath(repo.Path), Git.FindRepositoryRoot(repo.Path));
        Assert.Equal(GitService.AttributesLine + "\n", File.ReadAllText(Path.Combine(repo.Path, ".gitattributes")));
        var ignore = File.ReadAllText(Path.Combine(repo.Path, ".gitignore"));
        Assert.Contains("*.rvt", ignore);
        // Idempotent.
        Assert.False(GitService.EnsureAttributes(repo.Path, useLfs: true));
    }

    [Fact]
    public void FindRepositoryRootOutsideARepository()
    {
        using var dir = new TempRepo();
        Assert.Null(Git.FindRepositoryRoot(dir.Path));
    }

    [Fact]
    public void ExistingIfcAttributeIsKept()
    {
        using var repo = new TempRepo();
        var path = Path.Combine(repo.Path, ".gitattributes");
        File.WriteAllText(path, "*.ifc filter=lfs diff=lfs merge=lfs -text\n");
        Assert.False(GitService.EnsureAttributes(repo.Path, useLfs: false));
    }

    [Fact]
    public void CommitsWithTheGivenAuthorAndReadsHeadBack()
    {
        using var repo = new TempRepo();
        var git = Git;
        git.Initialise(repo.Path, useLfs: false);
        Directory.CreateDirectory(Path.Combine(repo.Path, "ifc"));
        var model = Path.Combine(repo.Path, "ifc", "Tower.ifc");
        File.WriteAllText(model, "ISO-10303-21;\nversion 1\n");

        Assert.False(git.WriteHeadVersion(repo.Path, "ifc/Tower.ifc", Path.Combine(repo.Path, "x")));

        var sha = git.Commit(repo.Path, new[] { "ifc/Tower.ifc", ".gitattributes", ".gitignore" },
            "First version", "Ayşe Yılmaz", "ayse@example.com");
        Assert.NotNull(sha);
        Assert.Equal(40, sha!.Length);
        var author = git.Run(repo.Path, "log", "-1", "--format=%an <%ae>|%s").Stdout.Trim();
        Assert.Equal("Ayşe Yılmaz <ayse@example.com>|First version", author);

        // Unchanged model: nothing to commit.
        Assert.Null(git.Commit(repo.Path, new[] { "ifc/Tower.ifc" }, "again", "A", "a@example.com"));

        File.WriteAllText(model, "ISO-10303-21;\nversion 2\n");
        var head = Path.Combine(repo.Path, "head.ifc");
        Assert.True(git.WriteHeadVersion(repo.Path, "ifc/Tower.ifc", head));
        Assert.Contains("version 1", File.ReadAllText(head));
    }

    [Fact]
    public void RelativePathRejectsFilesOutsideTheRepository()
    {
        Assert.Throws<ArgumentException>(() => GitService.RelativePath(@"C:\proj", @"C:\other\a.ifc"));
    }
}

public class GitHubRepositoryTests
{
    [Theory]
    [InlineData("https://github.com/kaan36875/bimdelta-samples.git")]
    [InlineData("https://github.com/kaan36875/bimdelta-samples")]
    [InlineData("https://someone@github.com/kaan36875/bimdelta-samples/")]
    [InlineData("git@github.com:kaan36875/bimdelta-samples.git")]
    [InlineData("ssh://git@github.com/kaan36875/bimdelta-samples.git")]
    public void ParsesTheUrlsGitAccepts(string url)
    {
        var repo = GitHubRepository.Parse(url);
        Assert.NotNull(repo);
        Assert.Equal("https://github.com/kaan36875/bimdelta-samples", repo!.Url);
    }

    [Theory]
    [InlineData("https://gitlab.com/a/b.git")]
    [InlineData(@"C:\remotes\model.git")]
    [InlineData("https://github.com/only-owner")]
    public void OtherRemotesAreNotGitHub(string url)
    {
        Assert.Null(GitHubRepository.Parse(url));
    }

    [Fact]
    public void CompareUrlOpensThePullRequestForm()
    {
        var repo = GitHubRepository.Parse("git@github.com:o/r.git")!;
        Assert.Equal("https://github.com/o/r/compare/main...feature/c%C3%BCr%C3%BC?expand=1",
            repo.CompareUrl("main", "feature/cürü"));
    }
}

public class ShareServiceTests
{
    private static GitService Git => GitService.Find() ?? throw new InvalidOperationException("git not found");

    [Theory]
    [InlineData("Thicken L2 slab", "thicken-l2-slab")]
    [InlineData("Kapı yangın sınıfı EI60'a çıktı", "kapi-yangin-sinifi-ei60-a-cikti")]
    [InlineData("  --  ", "model-change")]
    [InlineData(null, "model-change")]
    [InlineData("A very long message that goes on and on about the facade panels", "a-very-long-message-that-goes-on-and-on")]
    public void SuggestsABranchNameFromTheMessage(string? message, string expected)
    {
        Assert.Equal(expected, ShareService.SuggestBranchName(message));
    }

    private static string Save(GitService git, string root, string content, string message)
    {
        Directory.CreateDirectory(Path.Combine(root, "ifc"));
        File.WriteAllText(Path.Combine(root, "ifc", "Tower.ifc"), content);
        return git.Commit(root, new[] { "ifc/Tower.ifc", ".gitattributes", ".gitignore" }, message,
            "Ayşe Yılmaz", "ayse@example.com")!;
    }

    private static string Head(GitService git, string cwd, string rev) =>
        git.Run(cwd, "rev-parse", rev).Stdout.Trim();

    [Fact]
    public void FirstSharePublishesThenVersionsOnMainMoveToABranch()
    {
        using var remote = new TempRepo();
        using var repo = new TempRepo();
        var git = Git;
        Assert.True(git.Run(remote.Path, "init", "--bare", "--quiet", "--initial-branch=main").Ok);
        git.Initialise(repo.Path, useLfs: false);
        var first = Save(git, repo.Path, "version 1\n", "First version");
        git.AddRemote(repo.Path, remote.Path);
        var share = new ShareService(git, repo.Path);

        // An empty remote takes the history as its main branch.
        var published = share.Share(null);
        Assert.Equal(ShareOutcome.Published, published.Outcome);
        Assert.Null(published.WebUrl);
        Assert.Equal(first, Head(git, remote.Path, "main"));

        // Nothing saved since: nothing to review.
        Assert.Equal(ShareOutcome.NothingNew, share.Share("unused").Outcome);
        Assert.Equal("main", git.CurrentBranch(repo.Path));

        var second = Save(git, repo.Path, "version 2\n", "Thicken L2 slab");
        var plan = share.Plan();
        Assert.True(plan.NeedsBranchName);
        Assert.Equal("thicken-l2-slab", plan.SuggestedName);

        Assert.Throws<ArgumentException>(() => share.Share("bad..name"));
        Assert.Equal("main", git.CurrentBranch(repo.Path));

        var review = share.Share(plan.SuggestedName);
        Assert.Equal(ShareOutcome.ReadyForReview, review.Outcome);
        Assert.Equal("main", review.BaseBranch);
        Assert.Equal("thicken-l2-slab", git.CurrentBranch(repo.Path));
        // The new version is on the branch only; main is back where the remote has it.
        Assert.Equal(second, Head(git, remote.Path, "thicken-l2-slab"));
        Assert.Equal(first, Head(git, remote.Path, "main"));
        Assert.Equal(first, Head(git, repo.Path, "main"));

        // Later versions on the branch: pushed to the same branch.
        Assert.False(share.Plan().NeedsBranchName);
        var third = Save(git, repo.Path, "version 3\n", "Move door");
        Assert.Equal(ShareOutcome.ReadyForReview, share.Share(null).Outcome);
        Assert.Equal(third, Head(git, remote.Path, "thicken-l2-slab"));
    }

    [Fact]
    public void ShareNeedsARemote()
    {
        using var repo = new TempRepo();
        var git = Git;
        git.Initialise(repo.Path, useLfs: false);
        Save(git, repo.Path, "version 1\n", "First version");
        Assert.Null(new ShareService(git, repo.Path).Plan().RemoteUrl);
        Assert.Throws<GitException>(() => new ShareService(git, repo.Path).Share(null));
    }

    [Fact]
    public void WarnsWhenAColleaguesVersionIsMissing()
    {
        using var remote = new TempRepo();
        using var mine = new TempRepo();
        using var theirs = new TempRepo();
        var git = Git;
        Assert.True(git.Run(remote.Path, "init", "--bare", "--quiet", "--initial-branch=main").Ok);
        git.Initialise(mine.Path, useLfs: false);
        Save(git, mine.Path, "version 1\n", "First version");
        git.AddRemote(mine.Path, remote.Path);
        var share = new ShareService(git, mine.Path);
        Assert.Equal(ShareOutcome.Published, share.Share(null).Outcome);

        // A colleague's version reaches main (their pull request was merged).
        Assert.True(git.Run(theirs.Path, "clone", "--quiet", remote.Path, ".").Ok);
        File.WriteAllText(Path.Combine(theirs.Path, "ifc", "Tower.ifc"), "version 2 by Ali\n");
        git.Commit(theirs.Path, new[] { "ifc/Tower.ifc" }, "Column sizes", "Ali", "ali@example.com");
        File.WriteAllText(Path.Combine(theirs.Path, "notes.txt"), "not a model\n");
        git.Commit(theirs.Path, new[] { "notes.txt" }, "Notes", "Ali", "ali@example.com");
        Assert.True(git.Run(theirs.Path, "push", "--quiet", "origin", "main").Ok);

        // Meanwhile I saved a version from a model without Ali's change.
        Save(git, mine.Path, "version 2 by me\n", "Thicken slab");
        var behind = share.Share("thicken-slab");
        Assert.Equal(ShareOutcome.Behind, behind.Outcome);
        var missing = Assert.Single(behind.Missing);
        Assert.Equal(("Ali", "Column sizes"), (missing.Author, missing.Subject));
        // Nothing changed: still on main, nothing pushed.
        Assert.Equal("main", git.CurrentBranch(mine.Path));
        Assert.False(git.Run(remote.Path, "rev-parse", "--verify", "--quiet", "thicken-slab").Ok);

        var anyway = share.Share("thicken-slab", shareAnyway: true);
        Assert.Equal(ShareOutcome.ReadyForReview, anyway.Outcome);
        Assert.True(git.Run(remote.Path, "rev-parse", "--verify", "--quiet", "thicken-slab").Ok);
    }

    [Fact]
    public void OldAttributesLineGetsMergeBinary()
    {
        using var repo = new TempRepo();
        var path = Path.Combine(repo.Path, ".gitattributes");
        File.WriteAllText(path, "*.png binary\n*.ifc diff=ifc\n");
        Assert.True(GitService.EnsureAttributes(repo.Path, useLfs: false));
        Assert.Equal("*.png binary\n" + GitService.AttributesLine + "\n", File.ReadAllText(path));
        Assert.False(GitService.EnsureAttributes(repo.Path, useLfs: false));
    }
}
