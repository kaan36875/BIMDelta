using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using BIMDelta.Revit.Core;

namespace BIMDelta.Revit.UI;

/// <summary>Asks for a commit message while the change preview is computed in the background.</summary>
public sealed class CommitDialog : Window
{
    private readonly TextBox _message;
    private readonly TextBlock _preview;
    private readonly Button _commit;

    public CommitDialog(GitService git, BimDeltaCli? cli, string root, string relativePath, IntPtr owner)
    {
        Title = "BIMDelta: Save Version";
        Width = 520;
        SizeToContent = SizeToContent.Height;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        ShowInTaskbar = false;
        new WindowInteropHelper(this).Owner = owner;

        var panel = new StackPanel { Margin = new Thickness(16) };

        panel.Children.Add(new TextBlock
        {
            Text = relativePath,
            FontWeight = FontWeights.SemiBold,
            Margin = new Thickness(0, 0, 0, 2),
        });
        panel.Children.Add(new TextBlock
        {
            Text = root,
            Foreground = Brushes.Gray,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Margin = new Thickness(0, 0, 0, 12),
        });

        panel.Children.Add(new TextBlock { Text = "What changed in this version?", Margin = new Thickness(0, 0, 0, 4) });
        _message = new TextBox
        {
            AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap,
            MinHeight = 60,
            MaxHeight = 160,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        _message.TextChanged += (_, _) => _commit!.IsEnabled = _message.Text.Trim().Length > 0;
        panel.Children.Add(_message);

        panel.Children.Add(new TextBlock
        {
            Text = "Changes since the last version",
            Margin = new Thickness(0, 12, 0, 4),
        });
        _preview = new TextBlock
        {
            Text = "Comparing…",
            FontFamily = new FontFamily("Consolas"),
            Foreground = Brushes.DimGray,
            TextWrapping = TextWrapping.Wrap,
        };
        panel.Children.Add(new Border
        {
            Child = new ScrollViewer
            {
                Content = _preview,
                MaxHeight = 220,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            },
            Background = new SolidColorBrush(Color.FromRgb(0xF5, 0xF5, 0xF5)),
            Padding = new Thickness(8),
        });

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 16, 0, 0),
        };
        _commit = new Button { Content = "Save version", Padding = new Thickness(12, 4, 12, 4), IsDefault = false, IsEnabled = false };
        _commit.Click += (_, _) => DialogResult = true;
        var cancel = new Button { Content = "Cancel", Padding = new Thickness(12, 4, 12, 4), Margin = new Thickness(8, 0, 0, 0), IsCancel = true };
        buttons.Children.Add(_commit);
        buttons.Children.Add(cancel);
        panel.Children.Add(buttons);

        Content = panel;
        Loaded += (_, _) => _message.Focus();
        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter && Keyboard.Modifiers == ModifierKeys.Control && _commit.IsEnabled)
                DialogResult = true;
        };

        _ = LoadPreviewAsync(git, cli, root, relativePath);
    }

    public string Message => _message.Text.Trim();

    private async Task LoadPreviewAsync(GitService git, BimDeltaCli? cli, string root, string relativePath)
    {
        string text;
        try
        {
            text = await Task.Run(() => Preview(git, cli, root, relativePath));
        }
        catch (Exception e)
        {
            text = "Could not compare: " + e.Message;
        }
        _preview.Text = text;
    }

    private static string Preview(GitService git, BimDeltaCli? cli, string root, string relativePath)
    {
        if (cli == null)
            return "Install the bimdelta command line tool to see a preview:\n  pip install bimdelta";
        var previous = Path.Combine(Path.GetTempPath(), $"bimdelta-head-{Guid.NewGuid():N}.ifc");
        try
        {
            if (!git.WriteHeadVersion(root, relativePath, previous))
                return "First version of this model.";
            return cli.Diff(previous, Path.Combine(root, relativePath), root).Describe();
        }
        finally
        {
            try
            {
                File.Delete(previous);
            }
            catch (IOException)
            {
            }
        }
    }
}
