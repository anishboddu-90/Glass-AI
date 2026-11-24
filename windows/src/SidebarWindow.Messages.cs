using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Threading;

namespace GlassSidebar
{
    // The conversation: welcome screen, message views, streaming, edit / regenerate / read aloud.
    internal sealed partial class SidebarWindow
    {
        static readonly string SendGlyph = G(0xE74A), StopGlyph = G(0xE71A), CopyGlyph = G(0xE8C8), CheckGlyph = G(0xE73E),
                               RetryGlyph = G(0xE72C), EditGlyph = G(0xE70F), SpeakGlyph = G(0xE767), FileGlyph = G(0xE8A5), PdfGlyph = G(0xEA90);

        static readonly FontFamily UiFont = new FontFamily("Segoe UI Variable Text, Segoe UI");
        static readonly FontFamily IconFont = new FontFamily("Segoe Fluent Icons, Segoe MDL2 Assets");
        static readonly Brush ErrorBrush = Frozen(Color.FromRgb(0xFF, 0xB4, 0xB4));
        static readonly Brush Selection = Frozen(Color.FromArgb(0x88, 0xA0, 0xC8, 0xFF));

        // current conversation; saved to disk after every message
        ChatSession session = new ChatSession();
        List<ChatSession> allChats = new List<ChatSession>();
        List<ChatMessage> history { get { return session.Messages; } }
        CancellationTokenSource streamCts;
        int editingIndex = -1;

        StackPanel messages;
        ScrollViewer chatScroll;
        FrameworkElement empty;
        TextBlock greeting, emptyHint, subtitle;
        WrapPanel suggestions;
        Button jumpBtn;

        void InitConversation()
        {
            messages = F<StackPanel>("Messages");
            chatScroll = F<ScrollViewer>("ChatScroll");
            empty = F<FrameworkElement>("Empty");
            greeting = F<TextBlock>("Greeting");
            emptyHint = F<TextBlock>("EmptyHint");
            subtitle = F<TextBlock>("Subtitle");
            suggestions = F<WrapPanel>("Suggestions");
            jumpBtn = F<Button>("JumpBtn");
            jumpBtn.Click += delegate { ScrollToEnd(); };
            F<Button>("NewBtn").Click += delegate { NewChat(); InputFocus(); };
            chatScroll.ScrollChanged += delegate
            {
                bool away = chatScroll.ScrollableHeight - chatScroll.VerticalOffset > 120;
                if (away != (jumpBtn.Visibility == Visibility.Visible))
                {
                    if (away) { jumpBtn.Visibility = Visibility.Visible; Animate.Pop(jumpBtn, 0, 0.6); }
                    else Animate.PopOut(jumpBtn, delegate { jumpBtn.Visibility = Visibility.Collapsed; });
                }
                F<UIElement>("HeaderLine").Opacity = chatScroll.VerticalOffset > 4 ? 1 : 0;
            };
            BuildWelcome();
        }

        // ---------------- welcome ----------------

        void BuildWelcome()
        {
            int h = DateTime.Now.Hour;
            greeting.Text = h < 5 ? "Up late?" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
            var ideas = new[]
            {
                new object[] { 0xE7F4, "What's on my screen?", "@screen" },
                new object[] { 0xE8A5, "Summarize something", "Summarize this in a few bullet points:\n" },
                new object[] { 0xE897, "Explain a concept", "Explain this simply, like I'm new to it: " },
                new object[] { 0xE70F, "Draft a message", "Write a short, friendly message that " },
                new object[] { 0xE943, "Debug some code", "Help me find the bug in this code:\n" },
                new object[] { 0xE720, "Talk to me", "@voice" },
            };
            suggestions.Children.Clear();
            int i = 0;
            foreach (var idea in ideas)
            {
                string prompt = (string)idea[2];
                var row = new StackPanel { Orientation = Orientation.Horizontal };
                row.Children.Add(new TextBlock { Text = G((int)idea[0]), FontFamily = IconFont, FontSize = 12, Margin = new Thickness(0, 1, 8, 0), VerticalAlignment = VerticalAlignment.Center, Opacity = 0.85 });
                row.Children.Add(new TextBlock { Text = (string)idea[1], VerticalAlignment = VerticalAlignment.Center });
                var b = new Button { Style = (Style)root.FindResource("PillBtn"), Content = row, Margin = new Thickness(0, 0, 8, 8), Padding = new Thickness(12, 8, 14, 8) };
                b.Click += delegate
                {
                    if (prompt == "@screen") { AskAboutScreen(); return; }
                    if (prompt == "@voice") { ToggleVoice(); return; }
                    inputBox.Text = prompt;
                    inputBox.CaretIndex = prompt.Length;
                    InputFocus();
                };
                suggestions.Children.Add(b);
                Animate.Rise(b, 120 + 45 * i++, 10);
            }
            Animate.Rise(greeting, 0, 14);
            Animate.Rise(F<FrameworkElement>("GreetingSub"), 60, 14);
            var halo = (ScaleTransform)root.FindName("WelcomeHaloScale");
            var pulse = new DoubleAnimation(0.9, 1.25, TimeSpan.FromSeconds(2.4)) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = Animate.Smooth };
            halo.BeginAnimation(ScaleTransform.ScaleXProperty, pulse);
            halo.BeginAnimation(ScaleTransform.ScaleYProperty, pulse);
        }

        void ShowWelcome(bool show)
        {
            if (show == (empty.Visibility == Visibility.Visible)) return;
            empty.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
            if (show) BuildWelcome();
        }

        // ---------------- chats ----------------

        void NewChat()
        {
            if (streamCts != null) streamCts.Cancel();
            if (voice != null) voice.StopSpeaking();
            CancelEdit();
            session = new ChatSession();
            messages.Children.Clear();
            ClearPending();
            ShowSettings(false);
            ShowWelcome(true);
            UpdateTitle();
            RefreshChatList();
        }

        void PersistSession(ChatSession s)
        {
            if (s.Messages.Count == 0) return;
            if (s.Title == "New chat")
            {
                var first = s.Messages.Find(m => m.Role == "user");
                if (first != null) s.Title = ChatStore.MakeTitle(first.Content.Length > 0 ? first.Content : (first.Attachments.Count > 0 ? first.Attachments[0].Name : ""));
            }
            s.Provider = settings.Provider;
            s.Model = settings.Model;
            ChatStore.Save(s);
            allChats.Remove(s);
            allChats.Insert(0, s);
            allChats = ChatStore.Sort(allChats);
            if (s == session) UpdateTitle();
            RefreshChatList();
        }

        // after the first exchange, ask the model for a short title (best effort)
        async void SmartTitle(ChatSession s)
        {
            if (s.SmartTitled || s.Messages.Count < 2) return;
            s.SmartTitled = true;
            try
            {
                var first = s.Messages.Find(m => m.Role == "user");
                string q = first == null ? "" : first.Content;
                if (q.Trim().Length == 0) return;
                if (q.Length > 600) q = q.Substring(0, 600);
                string t = await AiClient.QuickAsync(settings, "Write a 2-5 word title for a chat that starts with this message. Reply with only the title, no quotes or punctuation at the end.\n\n" + q);
                t = (t ?? "").Trim().Trim('"', '\'', '.', '*', '#').Replace("\n", " ");
                if (t.Length > 2 && t.Length < 60) { s.Title = t; ChatStore.Save(s, false); if (s == session) UpdateTitle(); RefreshChatList(); }
            }
            catch { }
        }

        void UpdateTitle()
        {
            var title = F<TextBlock>("Title");
            string t = session.Messages.Count > 0 ? session.Title : "Glass";
            if (title.Text != t) { title.Text = t; Animate.Rise(title, 0, 6); }
        }

        // ---------------- sending ----------------

        void Send()
        {
            if (streamCts != null) { streamCts.Cancel(); return; } // button doubles as Stop
            string text = inputBox.Text.Trim();
            if (text.Length == 0 && pending.Count == 0) return;
            if (string.IsNullOrEmpty(settings.ApiKey)) { ShowSettings(true); keyStatus.Text = "Add an API key first."; return; }
            if (voice != null) voice.StopSpeaking();

            if (editingIndex >= 0)
            {
                // editing: drop that message and everything after it, then resend
                if (editingIndex < session.Messages.Count) session.Messages.RemoveRange(editingIndex, session.Messages.Count - editingIndex);
                editingIndex = -1;
                F<UIElement>("EditBanner").Visibility = Visibility.Collapsed;
                RenderAll(false);
            }

            var msg = new ChatMessage("user", text) { Attachments = new List<Attachment>(pending) };
            inputBox.Text = "";
            ClearPending();
            ShowWelcome(false);
            session.Messages.Add(msg);
            messages.Children.Add(UserView(msg, session.Messages.Count - 1, true));
            PersistSession(session);
            ScrollToEnd();
            RunReply();
        }

        void Regenerate()
        {
            if (streamCts != null) return;
            if (session.Messages.Count > 0 && session.Messages[session.Messages.Count - 1].Role == "assistant")
            {
                session.Messages.RemoveAt(session.Messages.Count - 1);
                if (messages.Children.Count > 0) messages.Children.RemoveAt(messages.Children.Count - 1);
            }
            if (session.Messages.Count == 0 || session.Messages[session.Messages.Count - 1].Role != "user") return;
            RunReply();
        }

        void BeginEdit(int index)
        {
            if (streamCts != null || index < 0 || index >= session.Messages.Count) return;
            var m = session.Messages[index];
            editingIndex = index;
            inputBox.Text = m.Content;
            inputBox.CaretIndex = inputBox.Text.Length;
            ClearPending();
            foreach (var a in m.Attachments) AddPending(a);
            var banner = F<FrameworkElement>("EditBanner");
            banner.Visibility = Visibility.Visible;
            Animate.Rise(banner, 0, 6);
            InputFocus();
        }

        void CancelEdit()
        {
            if (editingIndex < 0) return;
            editingIndex = -1;
            F<UIElement>("EditBanner").Visibility = Visibility.Collapsed;
            inputBox.Text = "";
            ClearPending();
        }

        async void RunReply()
        {
            var replySession = session;
            var reply = new ChatMessage("assistant", "") { Provider = settings.Provider, Model = settings.Model };
            RichTextBox body; FrameworkElement thinking; StackPanel actions;
            var view = AssistantView(reply, true, out body, out thinking, out actions);
            messages.Children.Add(view);
            ScrollToEnd();

            var cts = new CancellationTokenSource();
            streamCts = cts;
            UpdateSendButton();

            var sb = new System.Text.StringBuilder();
            var renderClock = Stopwatch.StartNew();
            var sendHistory = new List<ChatMessage>(replySession.Messages);
            Exception error = null;
            try
            {
                await AiClient.StreamAsync(settings, sendHistory, delegate (string d)
                {
                    Dispatcher.BeginInvoke(new Action(delegate
                    {
                        sb.Append(d);
                        if (thinking.Visibility == Visibility.Visible)
                        {
                            thinking.Visibility = Visibility.Collapsed;
                            body.Visibility = Visibility.Visible;
                            Animate.Fade(body, 1, 200);
                        }
                        if (renderClock.ElapsedMilliseconds > 40) // re-render ~25x/s with a live cursor
                        {
                            bool follow = NearBottom();
                            body.Document = Markdown.Render(sb.ToString() + " ▍");
                            renderClock.Restart();
                            if (follow) ScrollToEnd();
                        }
                    }));
                }, cts.Token);
            }
            catch (OperationCanceledException) { }
            catch (Exception ex) { error = ex; }   // C# 5: no await inside catch, so handled below

            await Dispatcher.InvokeAsync(new Action(delegate { })); // flush pending deltas
            bool stuck = NearBottom();
            thinking.Visibility = Visibility.Collapsed;
            body.Visibility = Visibility.Visible;
            body.Opacity = 1;

            reply.Content = sb.ToString();
            if (cts.IsCancellationRequested) reply.Content += reply.Content.Length > 0 ? "\n\n*Stopped.*" : "*Stopped.*";
            if (error != null) reply.Error = error.Message;
            if (reply.Content.Length > 0 || reply.Error != null)
            {
                replySession.Messages.Add(reply);
                PersistSession(replySession);
            }
            FillAssistantBody(body, reply);
            BuildAssistantActions(actions, reply, true);
            Animate.Rise(actions, 80, 6);

            streamCts = null;
            UpdateSendButton();
            if (stuck) ScrollToEnd();

            bool spoken = false;
            if (error == null && !cts.IsCancellationRequested && reply.Content.Length > 0)
            {
                if (settings.SpeakReplies || voiceMode) { EnsureVoice(); voice.Speak(reply.Content, settings.VoiceName, settings.VoiceRate); spoken = true; }
                SmartTitle(replySession);
            }
            if (voiceMode && !spoken) ResumeVoiceLoop();
        }

        bool NearBottom() { return chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 80; }

        void ScrollToEnd()
        {
            Dispatcher.BeginInvoke(new Action(delegate { chatScroll.ScrollToEnd(); }), DispatcherPriority.Background);
        }

        // ---------------- rendering ----------------

        void RenderAll(bool animate)
        {
            messages.Children.Clear();
            for (int i = 0; i < session.Messages.Count; i++)
            {
                var m = session.Messages[i];
                bool last = i == session.Messages.Count - 1;
                if (m.Role == "user") messages.Children.Add(UserView(m, i, animate && last));
                else
                {
                    RichTextBox body; FrameworkElement thinking; StackPanel actions;
                    var v = AssistantView(m, animate && last, out body, out thinking, out actions);
                    thinking.Visibility = Visibility.Collapsed;
                    body.Visibility = Visibility.Visible;
                    FillAssistantBody(body, m);
                    BuildAssistantActions(actions, m, last);
                    actions.Visibility = Visibility.Visible;
                    messages.Children.Add(v);
                }
            }
            ShowWelcome(session.Messages.Count == 0);
        }

        FrameworkElement UserView(ChatMessage m, int index, bool animate)
        {
            var outer = new StackPanel { Margin = new Thickness(44, 12, 0, 2), HorizontalAlignment = HorizontalAlignment.Right };

            // attachments above the bubble
            if (m.Attachments.Count > 0)
            {
                var wrap = new WrapPanel { HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 0, 0, 6) };
                foreach (var a in m.Attachments) wrap.Children.Add(AttachmentTile(a, false));
                outer.Children.Add(wrap);
            }

            if (m.Content.Length > 0)
            {
                var tb = new TextBox
                {
                    Text = m.Content, IsReadOnly = true, TextWrapping = TextWrapping.Wrap,
                    Background = Brushes.Transparent, BorderThickness = new Thickness(0),
                    Foreground = White, FontSize = 14, Padding = new Thickness(0), FontFamily = UiFont,
                    CaretBrush = Brushes.Transparent, SelectionBrush = Selection, Cursor = Cursors.IBeam
                };
                var bubble = new Border
                {
                    Child = tb, CornerRadius = new CornerRadius(20, 20, 6, 20), Padding = new Thickness(15, 10, 15, 11),
                    HorizontalAlignment = HorizontalAlignment.Right,
                    Background = new LinearGradientBrush(Color.FromArgb(0x4A, 0xFF, 0xFF, 0xFF), Color.FromArgb(0x30, 0xFF, 0xFF, 0xFF), 90),
                    BorderBrush = Frozen(Color.FromArgb(0x4D, 0xFF, 0xFF, 0xFF)), BorderThickness = new Thickness(1)
                };
                outer.Children.Add(bubble);
            }

            // hover actions: edit, copy
            var actions = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Opacity = 0, Margin = new Thickness(0, 2, 0, 0) };
            var edit = ActionButton(EditGlyph, "Edit & resend");
            edit.Click += delegate { BeginEdit(index); };
            var copy = ActionButton(CopyGlyph, "Copy");
            copy.Click += delegate { CopyWithTick(copy, m.Content); };
            actions.Children.Add(edit); actions.Children.Add(copy);
            outer.Children.Add(actions);
            outer.Background = Brushes.Transparent;
            outer.MouseEnter += delegate { Animate.Fade(actions, 1, 150); };
            outer.MouseLeave += delegate { Animate.Fade(actions, 0, 200); };

            if (animate) Animate.Rise(outer, 0, 14);
            return outer;
        }

        FrameworkElement AssistantView(ChatMessage m, bool animate, out RichTextBox body, out FrameworkElement thinking, out StackPanel actions)
        {
            var panel = new StackPanel { Margin = new Thickness(0, 14, 0, 4) };

            var who = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 6) };
            var orb = new Ellipse { Width = 20, Height = 20, Fill = (Brush)root.FindResource("Orb"), Margin = new Thickness(0, 0, 9, 0) };
            who.Children.Add(orb);
            who.Children.Add(new TextBlock { Text = Settings.Label(m.Provider), Foreground = White, FontWeight = FontWeights.SemiBold, FontSize = 13, FontFamily = UiFont, VerticalAlignment = VerticalAlignment.Center });
            who.Children.Add(new TextBlock { Text = "  " + m.Model, Foreground = DimText, FontSize = 11.5, FontFamily = UiFont, VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis, MaxWidth = 210 });
            panel.Children.Add(who);

            body = new RichTextBox
            {
                IsReadOnly = true, IsDocumentEnabled = true, Background = Brushes.Transparent, BorderThickness = new Thickness(0),
                Foreground = White, Padding = new Thickness(0), Margin = new Thickness(29, 0, 4, 0),
                CaretBrush = Brushes.Transparent, SelectionBrush = Selection, Visibility = Visibility.Collapsed, Opacity = 0,
                VerticalScrollBarVisibility = ScrollBarVisibility.Disabled, Cursor = Cursors.IBeam
            };
            body.Document = new FlowDocument();
            panel.Children.Add(body);

            thinking = ThinkingIndicator();
            panel.Children.Add(thinking);

            actions = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(24, 4, 0, 0), Visibility = Visibility.Collapsed };
            panel.Children.Add(actions);

            if (animate) Animate.Rise(panel, 0, 12);
            return panel;
        }

        void FillAssistantBody(RichTextBox body, ChatMessage m)
        {
            var doc = Markdown.Render(m.Content);
            if (m.Error != null)
            {
                var p = new Paragraph(new Run("⚠  " + m.Error)) { Foreground = ErrorBrush, Margin = new Thickness(0, m.Content.Length > 0 ? 8 : 0, 0, 0) };
                doc.Blocks.Add(p);
            }
            body.Document = doc;
        }

        void BuildAssistantActions(StackPanel actions, ChatMessage m, bool isLast)
        {
            actions.Children.Clear();
            actions.Visibility = Visibility.Visible;
            if (m.Content.Length > 0)
            {
                var copy = ActionButton(CopyGlyph, "Copy");
                copy.Click += delegate { CopyWithTick(copy, m.Content); };
                actions.Children.Add(copy);
                var speak = ActionButton(SpeakGlyph, "Read aloud");
                speak.Click += delegate
                {
                    EnsureVoice();
                    if (voice.Speaking) voice.StopSpeaking(); else voice.Speak(m.Content, settings.VoiceName, settings.VoiceRate);
                };
                actions.Children.Add(speak);
            }
            if (isLast)
            {
                var retry = ActionButton(RetryGlyph, "Regenerate");
                retry.Click += delegate { Regenerate(); };
                actions.Children.Add(retry);
            }
            if (m.Time > 0)
                actions.Children.Add(new TextBlock
                {
                    Text = new DateTime(m.Time, DateTimeKind.Utc).ToLocalTime().ToString("h:mm tt"), Foreground = Frozen(Color.FromArgb(0x66, 0xFF, 0xFF, 0xFF)),
                    FontSize = 10.5, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(6, 0, 0, 0)
                });
        }

        Button ActionButton(string glyph, string tip)
        {
            return new Button { Style = (Style)root.FindResource("ActionBtn"), Content = glyph, ToolTip = tip };
        }

        void CopyWithTick(Button b, string text)
        {
            try { Clipboard.SetText(text ?? ""); } catch { }
            b.Content = CheckGlyph;
            Animate.Pop(b, 0, 0.7);
            var t = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.2) };
            t.Tick += delegate { b.Content = CopyGlyph; t.Stop(); };
            t.Start();
        }

        // shimmering "Thinking" label + three bouncing dots
        FrameworkElement ThinkingIndicator()
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(29, 4, 0, 4) };
            var label = new TextBlock { Text = "Thinking", FontSize = 13.5, FontFamily = UiFont, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 10, 0) };
            var shimmer = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(1, 0), MappingMode = BrushMappingMode.RelativeToBoundingBox };
            shimmer.GradientStops.Add(new GradientStop(Color.FromArgb(0x66, 0xFF, 0xFF, 0xFF), 0));
            shimmer.GradientStops.Add(new GradientStop(Color.FromArgb(0xFF, 0xFF, 0xFF, 0xFF), 0.5));
            shimmer.GradientStops.Add(new GradientStop(Color.FromArgb(0x66, 0xFF, 0xFF, 0xFF), 1));
            var shift = new TranslateTransform();
            shimmer.RelativeTransform = shift;
            shift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-1, 1, TimeSpan.FromSeconds(1.4)) { RepeatBehavior = RepeatBehavior.Forever });
            label.Foreground = shimmer;
            row.Children.Add(label);
            for (int i = 0; i < 3; i++)
            {
                var dot = new Ellipse { Width = 6, Height = 6, Fill = White, Margin = new Thickness(0, 0, 4, 0), VerticalAlignment = VerticalAlignment.Center };
                var tt = new TranslateTransform();
                dot.RenderTransform = tt;
                var bounce = new DoubleAnimationUsingKeyFrames { RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromMilliseconds(i * 140) };
                bounce.KeyFrames.Add(new EasingDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.Zero)));
                bounce.KeyFrames.Add(new EasingDoubleKeyFrame(-5, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(260)), new SineEase { EasingMode = EasingMode.EaseOut }));
                bounce.KeyFrames.Add(new EasingDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(520)), new SineEase { EasingMode = EasingMode.EaseIn }));
                bounce.KeyFrames.Add(new EasingDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(1000))));
                tt.BeginAnimation(TranslateTransform.YProperty, bounce);
                dot.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.35, 1, TimeSpan.FromMilliseconds(500)) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromMilliseconds(i * 140) });
                row.Children.Add(dot);
            }
            return row;
        }
    }
}
