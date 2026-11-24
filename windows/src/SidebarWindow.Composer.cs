using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Threading;

namespace GlassSidebar
{
    // Composer: attachments (pick / drop / paste / screen), voice mode, quick model switcher, toasts.
    internal sealed partial class SidebarWindow
    {
        TextBox inputBox;
        TextBlock placeholder, modelChipText;
        Button sendBtn, micBtn;
        WrapPanel attachTray;
        readonly List<Attachment> pending = new List<Attachment>();

        // ---------------- init ----------------

        void InitComposer()
        {
            inputBox = F<TextBox>("InputBox");
            placeholder = F<TextBlock>("Placeholder");
            modelChipText = F<TextBlock>("ModelChipText");
            sendBtn = F<Button>("SendBtn");
            micBtn = F<Button>("MicBtn");
            attachTray = F<WrapPanel>("AttachTray");

            inputBox.TextChanged += delegate
            {
                placeholder.Visibility = inputBox.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
                UpdateSendButton();
            };
            inputBox.PreviewKeyDown += OnInputKey;
            DataObject.AddPastingHandler(inputBox, OnPaste);
            sendBtn.Click += delegate { Send(); };
            F<Button>("AttachBtn").Click += delegate { PickFiles(); };
            F<Button>("ScreenBtn").Click += delegate { AskAboutScreen(); };
            micBtn.Click += delegate { ToggleVoice(); };
            F<Button>("ModelChip").Click += delegate { ToggleModelMenu(); };
            F<Button>("CancelEditBtn").Click += delegate { CancelEdit(); };

            // drag & drop anywhere on the glass
            panel.DragEnter += OnDragEnter;
            panel.DragOver += OnDragOver;
            panel.DragLeave += delegate { HideDropOverlay(); };
            panel.Drop += OnDrop;

            // voice bars
            var bars = F<StackPanel>("VoiceBars");
            for (int i = 0; i < 7; i++)
                bars.Children.Add(new Rectangle { Width = 4, Height = 4, RadiusX = 2, RadiusY = 2, Fill = White, Margin = new Thickness(0, 0, 4, 0), VerticalAlignment = VerticalAlignment.Center });

            InitModelMenu();
            UpdateSendButton();
        }

        void OnInputKey(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.Enter)
            {
                if ((Keyboard.Modifiers & ModifierKeys.Shift) != 0)
                {
                    int i = inputBox.CaretIndex;
                    inputBox.Text = inputBox.Text.Insert(i, Environment.NewLine);
                    inputBox.CaretIndex = i + Environment.NewLine.Length;
                }
                else Send();
                e.Handled = true;
            }
            else if (e.Key == Key.Up && inputBox.Text.Length == 0 && streamCts == null)
            {
                // ↑ in an empty box edits your last message, like most chat apps
                int last = session.Messages.FindLastIndex(m => m.Role == "user");
                if (last >= 0) { BeginEdit(last); e.Handled = true; }
            }
        }

        void UpdateSendButton()
        {
            bool streaming = streamCts != null;
            string glyph = streaming ? StopGlyph : SendGlyph;
            if ((sendBtn.Content as string) != glyph) { sendBtn.Content = glyph; Animate.Pop(sendBtn, 0, 0.7); }
            sendBtn.ToolTip = streaming ? "Stop" : (editingIndex >= 0 ? "Resend (Enter)" : "Send (Enter)");
            sendBtn.IsEnabled = streaming || inputBox.Text.Trim().Length > 0 || pending.Count > 0;
        }

        // ---------------- attachments ----------------

        void AddPending(Attachment a)
        {
            if (a == null) return;
            pending.Add(a);
            var tile = AttachmentTile(a, true);
            attachTray.Children.Add(tile);
            if (attachTray.Visibility != Visibility.Visible) { attachTray.Visibility = Visibility.Visible; Animate.Rise(attachTray, 0, 6); }
            Animate.Pop(tile, 0, 0.6);
            UpdateSendButton();
        }

        void RemovePending(Attachment a, FrameworkElement tile)
        {
            pending.Remove(a);
            Animate.PopOut(tile, delegate
            {
                attachTray.Children.Remove(tile);
                if (pending.Count == 0) attachTray.Visibility = Visibility.Collapsed;
            });
            UpdateSendButton();
        }

        void ClearPending()
        {
            pending.Clear();
            attachTray.Children.Clear();
            attachTray.Visibility = Visibility.Collapsed;
            placeholder.Text = "Ask anything…";
            UpdateSendButton();
        }

        void AttachFiles(IEnumerable<string> paths)
        {
            foreach (var p in paths)
            {
                try { AddPending(Attachments.FromFile(p)); }
                catch (Exception ex) { ShowToast(ex.Message); }
            }
            InputFocus();
        }

        void PickFiles()
        {
            var dlg = new Microsoft.Win32.OpenFileDialog { Title = "Attach files", Multiselect = true, Filter = Attachments.FileFilter };
            suppressDeactivate = true;
            bool? ok;
            try { ok = dlg.ShowDialog(this); }
            finally { suppressDeactivate = false; }
            Activate();
            if (ok == true) AttachFiles(dlg.FileNames);
        }

        void AskAboutScreen()
        {
            if (mode == Mode.Hidden) return;
            if (InSettings) ShowSettings(false);
            try
            {
                var shot = Attachments.CaptureScreen(CurrentScreen());
                AddPending(shot);
                ShowToast("Screenshot attached — ask anything about it");
                if (inputBox.Text.Trim().Length == 0) placeholder.Text = "Ask about your screen…";
                FlashGlass();
            }
            catch (Exception ex) { ShowToast("Couldn't capture the screen: " + ex.Message); }
            InputFocus();
        }

        // camera-flash feel
        void FlashGlass()
        {
            var flash = new Border { Background = White, Opacity = 0.0, IsHitTestVisible = false, CornerRadius = new CornerRadius(RadiusDip) };
            panel.Children.Add(flash);
            var a = new DoubleAnimation(0.35, 0, TimeSpan.FromMilliseconds(380)) { EasingFunction = Animate.Out };
            a.Completed += delegate { panel.Children.Remove(flash); };
            flash.BeginAnimation(UIElement.OpacityProperty, a);
        }

        void OnPaste(object sender, DataObjectPastingEventArgs e)
        {
            if (e.DataObject.GetDataPresent(DataFormats.FileDrop))
            {
                var files = e.DataObject.GetData(DataFormats.FileDrop) as string[];
                if (files != null && files.Length > 0) { AttachFiles(files); e.CancelCommand(); return; }
            }
            if (!e.DataObject.GetDataPresent(DataFormats.UnicodeText) && Clipboard.ContainsImage())
            {
                try { AddPending(Attachments.FromClipboard()); ShowToast("Image pasted"); } catch (Exception ex) { ShowToast(ex.Message); }
                e.CancelCommand();
            }
        }

        void OnDragEnter(object sender, DragEventArgs e)
        {
            if (!e.Data.GetDataPresent(DataFormats.FileDrop)) return;
            var overlay = F<FrameworkElement>("DropOverlay");
            if (overlay.Visibility != Visibility.Visible) { overlay.Visibility = Visibility.Visible; Animate.Pop(overlay, 0, 0.96); }
            e.Effects = DragDropEffects.Copy; e.Handled = true;
        }

        void OnDragOver(object sender, DragEventArgs e)
        {
            e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
            e.Handled = true;
        }

        void HideDropOverlay()
        {
            var overlay = F<FrameworkElement>("DropOverlay");
            if (overlay.Visibility == Visibility.Visible) Animate.Fade(overlay, 0, 150, 0, delegate { overlay.Visibility = Visibility.Collapsed; overlay.Opacity = 1; });
        }

        void OnDrop(object sender, DragEventArgs e)
        {
            HideDropOverlay();
            var files = e.Data.GetData(DataFormats.FileDrop) as string[];
            if (files != null) { if (InSettings) ShowSettings(false); AttachFiles(files); }
            e.Handled = true;
        }

        // image thumbnail or file chip; removable ones get a ✕
        FrameworkElement AttachmentTile(Attachment a, bool removable)
        {
            var grid = new Grid { Margin = new Thickness(0, 0, 8, 6) };
            FrameworkElement face;
            if (a.Kind == "image")
            {
                var thumb = Attachments.Thumbnail(a, 300);
                face = new Border
                {
                    Width = removable ? 64 : 150, Height = removable ? 64 : 110, CornerRadius = new CornerRadius(14), ClipToBounds = true,
                    BorderBrush = Frozen(Color.FromArgb(0x50, 0xFF, 0xFF, 0xFF)), BorderThickness = new Thickness(1),
                    Background = thumb != null ? (Brush)new ImageBrush(thumb) { Stretch = Stretch.UniformToFill } : Frozen(Color.FromArgb(0x30, 0xFF, 0xFF, 0xFF)),
                    Cursor = Cursors.Hand, ToolTip = a.Name
                };
                face.MouseLeftButtonUp += delegate { OpenAttachment(a); };
            }
            else
            {
                var row = new StackPanel { Orientation = Orientation.Horizontal };
                var icon = new Border { Width = 34, Height = 34, CornerRadius = new CornerRadius(10), Background = Frozen(a.Kind == "pdf" ? Color.FromRgb(0xE5, 0x48, 0x4D) : Color.FromRgb(0x5E, 0x8B, 0xFF)) };
                icon.Child = new TextBlock { Text = a.Kind == "pdf" ? PdfGlyph : FileGlyph, FontFamily = IconFont, FontSize = 15, Foreground = White, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
                row.Children.Add(icon);
                var text = new StackPanel { Margin = new Thickness(10, 0, 4, 0), VerticalAlignment = VerticalAlignment.Center };
                text.Children.Add(new TextBlock { Text = a.Name, Foreground = White, FontSize = 12.5, MaxWidth = 150, TextTrimming = TextTrimming.CharacterEllipsis });
                text.Children.Add(new TextBlock { Text = (a.Kind == "pdf" ? "PDF" : "Text") + " · " + Attachments.SizeText(a.Bytes), Foreground = DimText, FontSize = 11 });
                row.Children.Add(text);
                face = new Border
                {
                    Child = row, Padding = new Thickness(6, 6, 12, 6), CornerRadius = new CornerRadius(14),
                    Background = Frozen(Color.FromArgb(0x26, 0xFF, 0xFF, 0xFF)), BorderBrush = Frozen(Color.FromArgb(0x40, 0xFF, 0xFF, 0xFF)), BorderThickness = new Thickness(1),
                    ToolTip = a.Name
                };
            }
            grid.Children.Add(face);
            if (removable)
            {
                var x = new Button
                {
                    Style = (Style)root.FindResource("IconBtn"), Content = G(0xE711), FontSize = 8, Width = 20, Height = 20,
                    Background = Frozen(Color.FromArgb(0xE6, 0x2A, 0x2C, 0x32)), HorizontalAlignment = HorizontalAlignment.Right,
                    VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, -6, -6, 0), ToolTip = "Remove"
                };
                x.Click += delegate { RemovePending(a, grid); };
                grid.Children.Add(x);
            }
            return grid;
        }

        void OpenAttachment(Attachment a)
        {
            try
            {
                string dir = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "GlassSidebar");
                Directory.CreateDirectory(dir);
                string ext = a.MediaType == "image/png" ? ".png" : ".jpg";
                string path = System.IO.Path.Combine(dir, Guid.NewGuid().ToString("N").Substring(0, 8) + ext);
                File.WriteAllBytes(path, Convert.FromBase64String(a.Data));
                System.Diagnostics.Process.Start(path);
            }
            catch { }
        }

        // ---------------- voice mode ----------------

        Voice voice;
        bool voiceMode;
        string voiceCommitted = "";
        DispatcherTimer voiceSendTimer;

        void EnsureVoice()
        {
            if (voice != null) return;
            voice = new Voice();
            voice.Partial += t => Dispatcher.BeginInvoke(new Action(delegate { F<TextBlock>("VoiceText").Text = (voiceCommitted + " " + t).Trim(); }));
            voice.Final += t => Dispatcher.BeginInvoke(new Action(delegate
            {
                voiceCommitted = (voiceCommitted + " " + t).Trim();
                F<TextBlock>("VoiceText").Text = voiceCommitted;
                voiceSendTimer.Stop(); voiceSendTimer.Start();   // send after a short pause
            }));
            voice.Level += l => Dispatcher.BeginInvoke(new Action(delegate { micLevel = Math.Max(micLevel * 0.6, l); }));
            voice.SpeakingChanged += speaking => Dispatcher.BeginInvoke(new Action(delegate
            {
                if (!speaking && voiceMode && streamCts == null) ResumeVoiceLoop();
            }));
            voiceSendTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(1300) };
            voiceSendTimer.Tick += delegate
            {
                voiceSendTimer.Stop();
                if (voiceCommitted.Length == 0) return;
                string text = voiceCommitted;
                voiceCommitted = "";
                voice.Stop();
                SetVoiceUi(false);
                inputBox.Text = text;
                Send();
            };
        }

        void ToggleVoice()
        {
            if (voiceMode) StopVoice();
            else
            {
                voiceMode = true;
                ShowToast("Voice mode — just talk. Pause to send, Esc to stop.");
                StartListening();
            }
        }

        void StartListening()
        {
            EnsureVoice();
            voice.StopSpeaking();
            try
            {
                voiceCommitted = "";
                voice.Start();
                SetVoiceUi(true);
            }
            catch (Exception ex)
            {
                voiceMode = false;
                SetVoiceUi(false);
                ShowToast(ex.Message);
            }
        }

        void ResumeVoiceLoop()
        {
            if (voiceMode && mode != Mode.Hidden) StartListening();
        }

        void StopVoice()
        {
            voiceMode = false;
            if (voice != null) { voice.Stop(); voice.StopSpeaking(); }
            if (voiceSendTimer != null) voiceSendTimer.Stop();
            if (voiceCommitted.Length > 0) { inputBox.Text = voiceCommitted; inputBox.CaretIndex = inputBox.Text.Length; }
            voiceCommitted = "";
            SetVoiceUi(false);
            InputFocus();
        }

        void SetVoiceUi(bool on)
        {
            var vp = F<FrameworkElement>("VoicePanel");
            if (on)
            {
                F<TextBlock>("VoiceText").Text = "Listening…";
                vp.Visibility = Visibility.Visible; Animate.Fade(vp, 1, 200);
                inputBox.Visibility = Visibility.Hidden; placeholder.Visibility = Visibility.Hidden;
                micBtn.Background = Frozen(Color.FromRgb(0xFF, 0x45, 0x3A));
                micBtn.Foreground = White;
                var pulse = F<UIElement>("MicPulse");
                var ps = (ScaleTransform)root.FindName("MicPulseScale");
                var grow = new DoubleAnimation(1, 1.8, TimeSpan.FromMilliseconds(1100)) { RepeatBehavior = RepeatBehavior.Forever, EasingFunction = Animate.Out };
                ps.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
                ps.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
                pulse.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.9, 0, TimeSpan.FromMilliseconds(1100)) { RepeatBehavior = RepeatBehavior.Forever });
            }
            else
            {
                vp.Visibility = Visibility.Collapsed;
                inputBox.Visibility = Visibility.Visible;
                placeholder.Visibility = inputBox.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
                micBtn.Background = voiceMode ? Frozen(Color.FromArgb(0x55, 0xFF, 0x45, 0x3A)) : Brushes.Transparent;
                var pulse = F<UIElement>("MicPulse");
                pulse.BeginAnimation(UIElement.OpacityProperty, null);
                pulse.Opacity = 0;
            }
        }

        // per-frame UI bits: voice bars
        void OnFrameUi(double t, double dt)
        {
            micLevel *= Math.Pow(0.2, dt);   // decay between level events
            var vp = F<FrameworkElement>("VoicePanel");
            if (vp.Visibility != Visibility.Visible) return;
            var bars = F<StackPanel>("VoiceBars");
            for (int i = 0; i < bars.Children.Count; i++)
            {
                var r = (Rectangle)bars.Children[i];
                double wave = 0.5 + 0.5 * Math.Sin(t * 9 + i * 0.9);
                double target = 4 + 22 * Math.Min(1, 0.12 + micLevel * 1.6) * (0.35 + 0.65 * wave);
                r.Height += (target - r.Height) * Math.Min(1, dt * 18);
            }
        }

        // ---------------- toast ----------------

        DispatcherTimer toastTimer;

        void ShowToast(string text)
        {
            var toast = F<Border>("Toast");
            F<TextBlock>("ToastText").Text = text;
            var shift = (TranslateTransform)root.FindName("ToastShift");
            toast.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(1, TimeSpan.FromMilliseconds(180)));
            shift.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(-10, 0, TimeSpan.FromMilliseconds(380)) { EasingFunction = Animate.Spring });
            if (toastTimer == null)
            {
                toastTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2.4) };
                toastTimer.Tick += delegate
                {
                    toastTimer.Stop();
                    F<Border>("Toast").BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, TimeSpan.FromMilliseconds(260)));
                };
            }
            toastTimer.Stop(); toastTimer.Start();
        }

        // ---------------- quick model switcher (Ctrl+K) ----------------

        readonly Dictionary<string, List<KeyValuePair<string, string>>> modelCache = new Dictionary<string, List<KeyValuePair<string, string>>>();
        static readonly string[] ClaudeModels = { "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1" };

        bool ModelMenuOpen { get { return F<UIElement>("ModelMenu").Visibility == Visibility.Visible; } }

        void InitModelMenu()
        {
            var menu = F<Grid>("ModelMenu");
            menu.MouseLeftButtonDown += (s, e) => { if (e.OriginalSource == menu) CloseModelMenu(); };
            var filter = F<TextBox>("ModelFilter");
            filter.TextChanged += delegate
            {
                F<TextBlock>("ModelFilterHint").Visibility = filter.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
                BuildModelMenu();
            };
            filter.PreviewKeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter)
                {
                    e.Handled = true;
                    var list = F<StackPanel>("ModelMenuList");
                    var firstItem = list.Children.OfType<Button>().FirstOrDefault();
                    if (firstItem != null && firstItem.Tag is string[]) { var tag = (string[])firstItem.Tag; SwitchModel(tag[0], tag[1]); }
                    else if (filter.Text.Trim().Length > 0) SwitchModel(settings.Provider, filter.Text.Trim());
                }
                else if (e.Key == Key.Escape) { CloseModelMenu(); e.Handled = true; }
            };
        }

        void ToggleModelMenu()
        {
            if (ModelMenuOpen) { CloseModelMenu(); return; }
            if (InSettings) ShowSettings(false);
            var menu = F<FrameworkElement>("ModelMenu");
            menu.Visibility = Visibility.Visible;
            var card = F<FrameworkElement>("ModelMenuCard");
            var sc = (ScaleTransform)root.FindName("ModelMenuScale");
            card.Opacity = 0;
            card.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(160)));
            sc.BeginAnimation(ScaleTransform.ScaleXProperty, new DoubleAnimation(0.9, 1, TimeSpan.FromMilliseconds(340)) { EasingFunction = Animate.Spring });
            sc.BeginAnimation(ScaleTransform.ScaleYProperty, new DoubleAnimation(0.9, 1, TimeSpan.FromMilliseconds(340)) { EasingFunction = Animate.Spring });
            var filter = F<TextBox>("ModelFilter");
            filter.Text = "";
            BuildModelMenu();
            LoadMenuModels();
            Dispatcher.BeginInvoke(new Action(delegate { filter.Focus(); Keyboard.Focus(filter); }), DispatcherPriority.Input);
        }

        void CloseModelMenu()
        {
            var menu = F<FrameworkElement>("ModelMenu");
            if (menu.Visibility != Visibility.Visible) return;
            menu.Visibility = Visibility.Collapsed;
            InputFocus();
        }

        async void LoadMenuModels()
        {
            foreach (var p in new[] { "gemini", "groq" })
            {
                if (modelCache.ContainsKey(p) || !settings.HasKey(p)) continue;
                try
                {
                    var list = await AiClient.ListModelsAsync(p, settings.KeyFor(p));
                    modelCache[p] = list;
                    if (ModelMenuOpen) BuildModelMenu();
                }
                catch { modelCache[p] = new List<KeyValuePair<string, string>>(); }
            }
        }

        void BuildModelMenu()
        {
            var list = F<StackPanel>("ModelMenuList");
            list.Children.Clear();
            string q = F<TextBox>("ModelFilter").Text.Trim();
            var seen = new HashSet<string>();
            int shown = 0;

            Action<string> header = title => list.Children.Add(new TextBlock { Text = title, Foreground = DimText, FontSize = 11, Margin = new Thickness(10, 8, 0, 4) });

            // recent
            var recents = (settings.RecentModels ?? new List<string>()).Select(r => r.Split('|')).Where(a => a.Length == 2 && settings.HasKey(a[0])).ToList();
            var recentMatches = recents.Where(a => Matches(q, a[0], a[1])).ToList();
            if (recentMatches.Count > 0)
            {
                header("Recent");
                foreach (var a in recentMatches) { list.Children.Add(MenuItem(a[0], a[1], a[1])); seen.Add(a[0] + "|" + a[1]); shown++; }
            }

            foreach (var p in new[] { "anthropic", "gemini", "groq", "openai" })
            {
                if (!settings.HasKey(p)) continue;
                var models = new List<KeyValuePair<string, string>>();
                if (p == "anthropic") models.AddRange(ClaudeModels.Select(m => new KeyValuePair<string, string>(m, m)));
                else if (modelCache.ContainsKey(p)) models.AddRange(modelCache[p]);
                if (p == settings.Provider && !models.Any(m => m.Key == settings.Model)) models.Insert(0, new KeyValuePair<string, string>(settings.Model, settings.Model));
                var match = models.Where(m => !seen.Contains(p + "|" + m.Key) && Matches(q, p, m.Key + " " + m.Value)).Take(40).ToList();
                if (match.Count == 0) continue;
                header(Settings.Label(p));
                foreach (var m in match) { list.Children.Add(MenuItem(p, m.Key, m.Value)); shown++; }
            }

            var status = F<TextBlock>("ModelMenuStatus");
            if (shown == 0 && q.Length > 0) status.Text = "Press Enter to use \"" + q + "\" with " + Settings.Label(settings.Provider) + ".";
            else if (!settings.HasKey(settings.Provider)) status.Text = "Add API keys in Settings to switch between providers.";
            else status.Text = "Add more providers' keys in Settings to see them here.";
        }

        static bool Matches(string q, string provider, string text)
        {
            if (q.Length == 0) return true;
            return text.IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0 || Settings.Label(provider).IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        Button MenuItem(string provider, string model, string display)
        {
            bool current = provider == settings.Provider && model == settings.Model;
            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var text = new StackPanel();
            text.Children.Add(new TextBlock { Text = display, Foreground = White, FontSize = 13, TextTrimming = TextTrimming.CharacterEllipsis });
            if (display != model) text.Children.Add(new TextBlock { Text = model, Foreground = DimText, FontSize = 10.5, TextTrimming = TextTrimming.CharacterEllipsis });
            grid.Children.Add(text);
            if (current)
            {
                var check = new TextBlock { Text = CheckGlyph, FontFamily = IconFont, FontSize = 12, Foreground = White, VerticalAlignment = VerticalAlignment.Center };
                Grid.SetColumn(check, 1);
                grid.Children.Add(check);
            }
            var b = new Button { Style = (Style)root.FindResource("ListItem"), Content = grid, Tag = new[] { provider, model }, Padding = new Thickness(10, 7, 10, 7) };
            if (current) b.Background = Frozen(Color.FromArgb(0x26, 0xFF, 0xFF, 0xFF));
            b.Click += delegate { SwitchModel(provider, model); };
            return b;
        }

        void SwitchModel(string provider, string model)
        {
            settings.Provider = provider;
            settings.Model = model;
            settings.RememberModel(model);
            try { settings.Save(); } catch { }
            var h = SettingsChanged; if (h != null) h();
            UpdateStatusText();
            CloseModelMenu();
            Animate.Pop(F<FrameworkElement>("ModelChip"), 0, 0.85);
            ShowToast("Now using " + Settings.Label(provider) + " · " + model);
        }
    }
}
