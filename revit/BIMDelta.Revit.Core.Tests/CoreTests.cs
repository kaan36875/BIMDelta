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
