using System;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace GlassSidebar
{
    // Saved-chats pane (fullscreen): new chat, search, grouped by date, pin, rename-free delete, export.
    internal sealed partial class SidebarWindow
    {
        StackPanel chatList;
        TextBox chatSearch;
        static readonly Brush ActiveItem = Frozen(Color.FromArgb(0x30, 0xFF, 0xFF, 0xFF));

        void InitChatList()
        {
            chatList = F<StackPanel>("ChatList");
            chatSearch = F<TextBox>("ChatSearch");
            allChats = ChatStore.LoadAll();

            F<Button>("PaneNewChat").Click += delegate { NewChat(); InputFocus(); };
            chatSearch.TextChanged += delegate
            {
                F<TextBlock>("ChatSearchHint").Visibility = chatSearch.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
                RefreshChatList();
            };
            RefreshChatList();
        }

        void ShowChatsPane(bool show)
        {
            var pane = F<FrameworkElement>("ChatsPane");
            bool was = pane.Visibility == Visibility.Visible;
            pane.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
            F<FrameworkElement>("HeaderOrbHost").Visibility = show ? Visibility.Collapsed : Visibility.Visible;
            if (show && !was) { RefreshChatList(true); Animate.SlideIn(pane, -60, 480); }
        }

        void RefreshChatList() { RefreshChatList(false); }

        void RefreshChatList(bool animate)
        {
            if (chatList == null) return;
            chatList.Children.Clear();
            string q = chatSearch.Text.Trim();
            var shown = allChats.Where(c => q.Length == 0 ||
                c.Title.IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0 ||
                c.Messages.Any(m => m.Content != null && m.Content.IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0)).ToList();

            if (shown.Count == 0)
            {
                chatList.Children.Add(new TextBlock
                {
                    Text = q.Length > 0 ? "No chats match." : "Your chats will show up here.",
                    Foreground = DimText, FontSize = 12, Margin = new Thickness(10, 6, 0, 0), TextWrapping = TextWrapping.Wrap
                });
                return;
            }

            string lastBucket = null;
            int i = 0;
            foreach (var chat in shown)
            {
                var c = chat;
                string bucket = ChatStore.Bucket(c);
                if (bucket != lastBucket)
                {
                    chatList.Children.Add(new TextBlock { Text = bucket, Foreground = DimText, FontSize = 11, Margin = new Thickness(10, lastBucket == null ? 2 : 14, 0, 4) });
                    lastBucket = bucket;
                }

                var grid = new Grid();
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

                var text = new StackPanel();
                text.Children.Add(new TextBlock { Text = c.Title, FontSize = 13, Foreground = White, TextTrimming = TextTrimming.CharacterEllipsis, FontFamily = UiFont });
                text.Children.Add(new TextBlock { Text = ChatStore.RelativeTime(c.Updated) + " · " + Settings.Label(c.Provider), FontSize = 11, Foreground = DimText, Margin = new Thickness(0, 2, 0, 0), FontFamily = UiFont });
                grid.Children.Add(text);

                var tools = new StackPanel { Orientation = Orientation.Horizontal, Opacity = 0, VerticalAlignment = VerticalAlignment.Center };
                var pin = new Button { Style = (Style)root.FindResource("ActionBtn"), Content = G(c.Pinned ? 0xE77A : 0xE718), ToolTip = c.Pinned ? "Unpin" : "Pin to top" };
                var export = new Button { Style = (Style)root.FindResource("ActionBtn"), Content = G(0xE8C8), ToolTip = "Copy chat as Markdown" };
                var del = new Button { Style = (Style)root.FindResource("ActionBtn"), Content = G(0xE74D), ToolTip = "Delete chat" };
                tools.Children.Add(pin); tools.Children.Add(export); tools.Children.Add(del);
                Grid.SetColumn(tools, 1);
                grid.Children.Add(tools);

                var item = new Button { Style = (Style)root.FindResource("ListItem"), Content = grid };
                if (c == session) item.Background = ActiveItem;
                item.MouseEnter += delegate { Animate.Fade(tools, 1, 120); };
                item.MouseLeave += delegate { Animate.Fade(tools, 0, 160); };
                item.Click += delegate { LoadSession(c); };
                pin.Click += delegate (object s, RoutedEventArgs e)
                {
                    e.Handled = true;
                    c.Pinned = !c.Pinned;
                    ChatStore.Save(c, false);
                    allChats = ChatStore.Sort(allChats);
                    RefreshChatList();
                };
                export.Click += delegate (object s, RoutedEventArgs e)
                {
                    e.Handled = true;
                    try { Clipboard.SetText(ChatStore.Export(c)); ShowToast("Chat copied as Markdown"); } catch { }
                };
                del.Click += delegate (object s, RoutedEventArgs e)
                {
                    e.Handled = true; // don't also open it
                    ChatStore.Delete(c.Id);
                    allChats.Remove(c);
                    if (c == session) NewChat(); else RefreshChatList();
                    ShowToast("Chat deleted");
                };
                chatList.Children.Add(item);
                if (animate && i < 20) Animate.Rise(item, 60 + i * 28, 8);
                i++;
            }
        }

        void LoadSession(ChatSession s)
        {
            if (s == session) return;
            if (streamCts != null) streamCts.Cancel();
            if (voice != null) voice.StopSpeaking();
            CancelEdit();
            session = s;
            ClearPending();
            ShowSettings(false);
            RenderAll(false);
            // stagger the last few messages in
            int n = messages.Children.Count;
            for (int k = Math.Max(0, n - 6); k < n; k++) Animate.Rise((FrameworkElement)messages.Children[k], (k - Math.Max(0, n - 6)) * 40, 10);
            UpdateTitle();
            RefreshChatList();
            ScrollToEnd();
            InputFocus();
        }
    }
}
