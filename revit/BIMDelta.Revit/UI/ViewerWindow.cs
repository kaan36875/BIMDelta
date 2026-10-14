using System;
using System.IO;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Interop;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace BIMDelta.Revit.UI;

/// <summary>The diff viewer in a Revit-owned window, using the WebView2 that Revit ships.</summary>
public sealed class ViewerWindow : Window
{
    private ViewerWindow(string url, string title, IntPtr owner)
    {
        Title = $"BIMDelta: {title}";
        Width = 1400;
        Height = 860;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        new WindowInteropHelper(this).Owner = owner;

        var view = new WebView2();
        Content = view;
        Loaded += async (_, _) =>
        {
            try
            {
                // A user data folder of our own: Revit's install folder is not writable.
                var env = await CoreWebView2Environment.CreateAsync(null,
                    Path.Combine(App.DataFolder, "WebView2"));
                await view.EnsureCoreWebView2Async(env);
                view.Source = new Uri(url);
            }
            catch (Exception e)
            {
                MessageBox.Show(this, "The viewer could not load: " + e.Message, "BIMDelta");
                Close();
            }
        };
    }

    /// <summary>Show the viewer; false when WebView2 is not available in this Revit.</summary>
    public static bool TryShow(string url, string title, IntPtr owner)
    {
        try
        {
            Show(url, title, owner);
            return true;
        }
        // Matched by name: naming the WebView2 type here would itself need the assembly.
        catch (Exception e) when (e is FileNotFoundException or FileLoadException or TypeLoadException
                                       || e.GetType().Name == "WebView2RuntimeNotFoundException")
        {
            return false;
        }
    }

    // Separate method: WebView2 types are only loaded when it runs, so a missing assembly
    // surfaces as a catchable exception in TryShow.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Show(string url, string title, IntPtr owner)
    {
        CoreWebView2Environment.GetAvailableBrowserVersionString();
        new ViewerWindow(url, title, owner).Show();
    }
}
