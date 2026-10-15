using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Interop;
using System.Windows.Media;
using BIMDelta.Revit.Core;

namespace BIMDelta.Revit.UI;

/// <summary>Connects the project to a remote if needed, asks for a branch name on main, and
/// pushes in the background.</summary>
public sealed class ShareDialog : Window
{
    private const string NewRepositoryUrl = "https://github.com/new";

    private readonly GitService _git;
    private readonly string _root;
    private readonly TextBox? _remote;
    private readonly TextBox? _branch;
    private readonly TextBlock _status;
    private readonly Button _share;
    private bool _shareAnyway;

    public ShareDialog(GitService git, string root, SharePlan plan, IntPtr owner)
    {
        _git = git;
        _root = root;
        Title = "BIMDelta: Share for Review";
        Width = 520;
        SizeToContent = SizeToContent.Height;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        ShowInTaskbar = false;
        new WindowInteropHelper(this).Owner = owner;

        var panel = new StackPanel { Margin = new Thickness(16) };

        if (plan.RemoteUrl == null)
        {
            panel.Children.Add(Heading("Connect this project to GitHub"));
            var help = Note("Create an empty repository (without a README) at ");
            var link = new Hyperlink(new Run(NewRepositoryUrl)) { NavigateUri = new Uri(NewRepositoryUrl) };
            link.RequestNavigate += (_, e) => OpenInBrowser(e.Uri.AbsoluteUri);
            help.Inlines.Add(link);
            help.Inlines.Add(" and paste its address here:");
            panel.Children.Add(help);
            _remote = new TextBox { Margin = new Thickness(0, 0, 0, 12) };
            _remote.TextChanged += (_, _) => UpdateShareButton();
            panel.Children.Add(_remote);
        }
        else
        {
            panel.Children.Add(Heading("Repository"));
            panel.Children.Add(Note(plan.RemoteUrl, 12));
        }

        if (plan.NeedsBranchName)
        {
            panel.Children.Add(Heading("Name this change"));
            _branch = new TextBox { Text = plan.SuggestedName };
            _branch.TextChanged += (_, _) => UpdateShareButton();
            panel.Children.Add(_branch);
            panel.Children.Add(Note(
                $"The versions you saved go to a branch with this name, and you open a pull request " +
                $"from it. {plan.BaseBranch} changes only when the pull request is merged.", 0));
        }
        else
        {
            panel.Children.Add(Heading("Branch"));
            panel.Children.Add(Note($"{plan.Branch}, for review into {plan.BaseBranch}", 0));
        }

        _status = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) };
        panel.Children.Add(_status);

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 16, 0, 0),
        };
        _share = new Button { Content = "Share", Padding = new Thickness(12, 4, 12, 4), IsDefault = true };
        _share.Click += async (_, _) => await ShareAsync();
        var cancel = new Button { Content = "Cancel", Padding = new Thickness(12, 4, 12, 4), Margin = new Thickness(8, 0, 0, 0), IsCancel = true };
        buttons.Children.Add(_share);
        buttons.Children.Add(cancel);
        panel.Children.Add(buttons);

        Content = panel;
        Loaded += (_, _) => (_remote ?? _branch)?.Focus();
        UpdateShareButton();
    }

    /// <summary>Set when the push succeeded.</summary>
    public ShareResult? Result { get; private set; }

    public static void OpenInBrowser(string url) =>
        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

    private static TextBlock Heading(string text) =>
        new() { Text = text, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 4) };

    private static TextBlock Note(string text, double bottom = 4) => new()
    {
        Text = text,
        Foreground = Brushes.Gray,
        TextWrapping = TextWrapping.Wrap,
        Margin = new Thickness(0, 2, 0, bottom),
    };

    private void UpdateShareButton()
    {
        _share.IsEnabled = (_remote == null || _remote.Text.Trim().Length > 0) &&
                           (_branch == null || _branch.Text.Trim().Length > 0);
    }

    private async Task ShareAsync()
    {
        var remote = _remote?.Text.Trim();
        var branch = _branch?.Text.Trim();
        _share.IsEnabled = false;
        _status.Foreground = Brushes.DimGray;
        _status.Text = "Checking GitHub… The first time, a GitHub sign-in window may open.";
        var anyway = _shareAnyway;
        try
        {
            Result = await Task.Run(() =>
            {
                if (remote != null && _git.RemoteUrl(_root, ShareService.Remote) == null)
                    _git.AddRemote(_root, remote, ShareService.Remote);
                return new ShareService(_git, _root).Share(branch, anyway);
            });
        }
        catch (Exception e) when (e is GitException or ArgumentException or TimeoutException)
        {
            _status.Foreground = Brushes.Firebrick;
            _status.Text = e.Message;
            UpdateShareButton();
            return;
        }

        if (Result.Outcome == ShareOutcome.NothingNew)
        {
            _status.Text = $"Every saved version is already on {Result.BaseBranch}. " +
                           "Save a version with your change first." +
                           (Result.Missing.Count > 0
                               ? $"\n\n{Result.BaseBranch} also has newer versions than your model:\n" +
                                 List(Result.Missing) + "\nUpdate the model before you change it."
                               : "");
            Result = null;
            return;
        }
        if (Result.Outcome == ShareOutcome.Behind)
        {
            var n = Result.Missing.Count;
            _status.Foreground = Brushes.DarkGoldenrod;
            _status.Text =
                $"{Result.BaseBranch} has {n} model version{(n == 1 ? "" : "s")} that your model does not include:\n" +
                List(Result.Missing) +
                "\n\nYour pull request would undo them. Bring them into the model first (with a " +
                "central model: Synchronize with Central), then Save Version and Share again.";
            _shareAnyway = true;
            _share.Content = "Share anyway";
            _share.IsDefault = false;
            Result = null;
            UpdateShareButton();
            return;
        }
        DialogResult = true;
    }

    private static string List(IReadOnlyList<CommitInfo> commits) =>
        string.Join("\n", commits.Take(5).Select(c => "  • " + c)) +
        (commits.Count > 5 ? $"\n  • and {commits.Count - 5} more" : "");
}
