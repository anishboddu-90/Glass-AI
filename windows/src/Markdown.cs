using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;

namespace GlassSidebar
{
    // Forgiving Markdown -> FlowDocument renderer for chat replies.
    // Headings, lists, quotes, tables, fenced code (with a copy button), **bold**, *italic*, `code`, [links](url).
    internal static class Markdown
    {
        static readonly FontFamily Body = new FontFamily("Segoe UI Variable Text, Segoe UI");
        static readonly FontFamily Mono = new FontFamily("Cascadia Code, Cascadia Mono, Consolas");
        static readonly FontFamily Icons = new FontFamily("Segoe Fluent Icons, Segoe MDL2 Assets");
        static readonly Brush Text = Frozen(Color.FromArgb(0xF2, 0xFF, 0xFF, 0xFF));
        static readonly Brush Dim = Frozen(Color.FromArgb(0xA6, 0xFF, 0xFF, 0xFF));
        static readonly Brush CodeBg = Frozen(Color.FromArgb(0x52, 0x00, 0x00, 0x08));
        static readonly Brush CodeHeader = Frozen(Color.FromArgb(0x30, 0x00, 0x00, 0x08));
        static readonly Brush Hairline = Frozen(Color.FromArgb(0x26, 0xFF, 0xFF, 0xFF));
        static readonly Brush InlineCodeBg = Frozen(Color.FromArgb(0x2E, 0xFF, 0xFF, 0xFF));
        static readonly Brush Link = Frozen(Color.FromRgb(0xA8, 0xD8, 0xFF));
        static readonly Regex Inline = new Regex(@"(\*\*(.+?)\*\*)|(`([^`]+)`)|(\[([^\]]+)\]\((https?://[^)\s]+)\))|((?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*]))|(~~(.+?)~~)", RegexOptions.Compiled);

        static Brush Frozen(Color c) { var b = new SolidColorBrush(c); b.Freeze(); return b; }

        public static FlowDocument Render(string md)
        {
            var doc = new FlowDocument
            {
                FontFamily = Body, FontSize = 14, Foreground = Text, PagePadding = new Thickness(0),
                LineHeight = 22, TextAlignment = TextAlignment.Left
            };
            string[] lines = (md ?? "").Replace("\r\n", "\n").Split('\n');
            int i = 0;
            while (i < lines.Length)
            {
                string line = lines[i];
                string t = line.TrimStart();

                if (t.StartsWith("```"))
                {
                    string lang = t.Substring(3).Trim();
                    var code = new System.Text.StringBuilder();
                    i++;
                    while (i < lines.Length && !lines[i].TrimStart().StartsWith("```"))
                    {
                        if (code.Length > 0) code.Append('\n');
                        code.Append(lines[i]); i++;
                    }
                    i++; // closing fence (or end while streaming)
                    doc.Blocks.Add(CodeBlock(code.ToString(), lang));
                    continue;
                }

                if (t.Length == 0) { i++; continue; }

                // table: header row, then |---|---| separator
                if (t.StartsWith("|") && i + 1 < lines.Length && Regex.IsMatch(lines[i + 1].Trim(), @"^\|?\s*:?-{2,}"))
                {
                    var rows = new List<string[]>();
                    rows.Add(Cells(t));
                    i += 2;
                    while (i < lines.Length && lines[i].TrimStart().StartsWith("|")) { rows.Add(Cells(lines[i].Trim())); i++; }
                    doc.Blocks.Add(TableBlock(rows));
                    continue;
                }

                var h = Regex.Match(t, @"^(#{1,6})\s+(.*)$");
                if (h.Success)
                {
                    int level = h.Groups[1].Length;
                    var p = Para(h.Groups[2].Value);
                    p.FontWeight = FontWeights.SemiBold;
                    p.FontFamily = new FontFamily("Segoe UI Variable Display, Segoe UI");
                    p.FontSize = level == 1 ? 20 : level == 2 ? 17.5 : 15.5;
                    p.Margin = new Thickness(0, 12, 0, 4);
                    doc.Blocks.Add(p); i++; continue;
                }

                if (Regex.IsMatch(t, @"^([-*_])\1{2,}$"))
                {
                    doc.Blocks.Add(new Paragraph { Margin = new Thickness(0, 6, 0, 10), BorderBrush = Hairline, BorderThickness = new Thickness(0, 0, 0, 1), FontSize = 2 });
                    i++; continue;
                }

                var bullet = Regex.Match(line, @"^(\s*)([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$");
                if (bullet.Success)
                {
                    int indent = bullet.Groups[1].Value.Replace("\t", "    ").Length / 2;
                    string raw = bullet.Groups[2].Value;
                    string marker = char.IsDigit(raw[0]) ? raw.TrimEnd(')', '.') + "." : (indent > 0 ? "◦" : "•");
                    if (bullet.Groups[3].Success) marker = bullet.Groups[3].Value.Trim().ToLower() == "[x]" ? "☑" : "☐";
                    var p = new Paragraph { Margin = new Thickness(4 + indent * 18, 2, 0, 2), TextIndent = 0 };
                    p.Inlines.Add(new Run(marker + "  ") { Foreground = Dim });
                    AddInlines(p.Inlines, bullet.Groups[4].Value);
                    doc.Blocks.Add(p); i++; continue;
                }

                if (t.StartsWith(">"))
                {
                    var p = Para(t.TrimStart('>', ' '));
                    p.Foreground = Dim;
                    p.BorderBrush = Frozen(Color.FromArgb(0x70, 0xFF, 0xFF, 0xFF));
                    p.BorderThickness = new Thickness(2, 0, 0, 0);
                    p.Padding = new Thickness(12, 2, 0, 2);
                    p.Margin = new Thickness(0, 4, 0, 6);
                    doc.Blocks.Add(p); i++; continue;
                }

                // plain paragraph: merge consecutive text lines
                var para = new Paragraph { Margin = new Thickness(0, 0, 0, 10) };
                bool first = true;
                while (i < lines.Length)
                {
                    string l = lines[i], lt = l.TrimStart();
                    if (lt.Length == 0 || lt.StartsWith("```") || lt.StartsWith("#") || lt.StartsWith(">") || lt.StartsWith("|") ||
                        Regex.IsMatch(l, @"^\s*([-*+]|\d+[.)])\s+")) break;
                    if (!first) para.Inlines.Add(new LineBreak());
                    AddInlines(para.Inlines, l);
                    first = false; i++;
                }
                doc.Blocks.Add(para);
            }
            if (doc.Blocks.Count > 0)
            {
                var last = doc.Blocks.LastBlock;
                last.Margin = new Thickness(last.Margin.Left, last.Margin.Top, last.Margin.Right, 0);
            }
            return doc;
        }

        static string[] Cells(string row)
        {
            string r = row.Trim();
            if (r.StartsWith("|")) r = r.Substring(1);
            if (r.EndsWith("|")) r = r.Substring(0, r.Length - 1);
            var parts = r.Split('|');
            for (int k = 0; k < parts.Length; k++) parts[k] = parts[k].Trim();
            return parts;
        }

        static Block TableBlock(List<string[]> rows)
        {
            int cols = 0;
            foreach (var r in rows) cols = Math.Max(cols, r.Length);
            var table = new Table { CellSpacing = 0, Margin = new Thickness(0, 4, 0, 12), BorderBrush = Hairline, BorderThickness = new Thickness(1) };
            for (int c = 0; c < cols; c++) table.Columns.Add(new TableColumn());
            var group = new TableRowGroup();
            for (int ri = 0; ri < rows.Count; ri++)
            {
                var tr = new TableRow();
                if (ri == 0) { tr.Background = Frozen(Color.FromArgb(0x22, 0xFF, 0xFF, 0xFF)); tr.FontWeight = FontWeights.SemiBold; }
                for (int c = 0; c < cols; c++)
                {
                    var p = new Paragraph { Margin = new Thickness(0), FontSize = 13 };
                    AddInlines(p.Inlines, c < rows[ri].Length ? rows[ri][c] : "");
                    tr.Cells.Add(new TableCell(p) { Padding = new Thickness(10, 6, 10, 6), BorderBrush = Hairline, BorderThickness = new Thickness(0, 0, c < cols - 1 ? 1 : 0, ri < rows.Count - 1 ? 1 : 0) });
                }
                group.Rows.Add(tr);
            }
            table.RowGroups.Add(group);
            return table;
        }

        static Paragraph Para(string text)
        {
            var p = new Paragraph();
            AddInlines(p.Inlines, text);
            return p;
        }

        // Code block: header bar with language + copy button, then monospace body.
        static Block CodeBlock(string code, string lang)
        {
            var header = new Grid { Background = CodeHeader };
            header.Children.Add(new TextBlock
            {
                Text = lang.Length > 0 ? lang : "code", Foreground = Dim, FontSize = 11, FontFamily = Body,
                Margin = new Thickness(12, 6, 0, 6), VerticalAlignment = VerticalAlignment.Center
            });
            var copyLabel = new TextBlock { Text = "Copy", FontSize = 11, FontFamily = Body, VerticalAlignment = VerticalAlignment.Center };
            var copyIcon = new TextBlock { Text = ((char)0xE8C8).ToString(), FontFamily = Icons, FontSize = 11, Margin = new Thickness(0, 0, 6, 0), VerticalAlignment = VerticalAlignment.Center };
            var row = new StackPanel { Orientation = Orientation.Horizontal };
            row.Children.Add(copyIcon); row.Children.Add(copyLabel);
            var copy = new Button
            {
                Content = row, Foreground = Dim, Background = Brushes.Transparent, BorderThickness = new Thickness(0),
                Padding = new Thickness(8, 3, 10, 3), Margin = new Thickness(0, 0, 4, 0), Cursor = System.Windows.Input.Cursors.Hand,
                HorizontalAlignment = HorizontalAlignment.Right, Focusable = false
            };
            copy.Template = FlatTemplate();
            copy.Click += delegate
            {
                try { Clipboard.SetText(code); } catch { }
                copyLabel.Text = "Copied"; copyIcon.Text = ((char)0xE73E).ToString();
                var timer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(1.4) };
                timer.Tick += delegate { copyLabel.Text = "Copy"; copyIcon.Text = ((char)0xE8C8).ToString(); timer.Stop(); };
                timer.Start();
            };
            header.Children.Add(copy);

            var body = new TextBox
            {
                Text = code, IsReadOnly = true, FontFamily = Mono, FontSize = 12.5, Foreground = Text,
                Background = Brushes.Transparent, BorderThickness = new Thickness(0), Padding = new Thickness(12, 10, 12, 12),
                HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled,
                TextWrapping = TextWrapping.NoWrap, CaretBrush = Brushes.Transparent,
                SelectionBrush = Frozen(Color.FromArgb(0x88, 0xA0, 0xC8, 0xFF))
            };

            var stack = new StackPanel();
            stack.Children.Add(header);
            stack.Children.Add(body);
            var card = new Border
            {
                Child = stack, Background = CodeBg, CornerRadius = new CornerRadius(12), ClipToBounds = true,
                BorderBrush = Hairline, BorderThickness = new Thickness(1)
            };
            return new BlockUIContainer(card) { Margin = new Thickness(0, 4, 0, 12) };
        }

        static ControlTemplate FlatTemplate()
        {
            var t = new ControlTemplate(typeof(Button));
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(7));
            border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(Control.PaddingProperty));
            border.SetValue(Border.BackgroundProperty, Brushes.Transparent);
            border.Name = "B";
            var cp = new FrameworkElementFactory(typeof(ContentPresenter));
            border.AppendChild(cp);
            t.VisualTree = border;
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(Border.BackgroundProperty, Frozen(Color.FromArgb(0x22, 0xFF, 0xFF, 0xFF)), "B"));
            t.Triggers.Add(hover);
            return t;
        }

        static void AddInlines(InlineCollection into, string text)
        {
            int pos = 0;
            foreach (Match m in Inline.Matches(text))
            {
                if (m.Index > pos) into.Add(new Run(text.Substring(pos, m.Index - pos)));
                if (m.Groups[1].Success) into.Add(new Bold(new Run(m.Groups[2].Value)));
                else if (m.Groups[3].Success)
                    into.Add(new Run(" " + m.Groups[4].Value + " ") { FontFamily = Mono, FontSize = 12.5, Background = InlineCodeBg });
                else if (m.Groups[5].Success)
                {
                    var link = new Hyperlink(new Run(m.Groups[6].Value)) { Foreground = Link, Cursor = System.Windows.Input.Cursors.Hand, TextDecorations = null };
                    string url = m.Groups[7].Value;
                    link.ToolTip = url;
                    link.Click += delegate { try { System.Diagnostics.Process.Start(url); } catch { } };
                    into.Add(link);
                }
                else if (m.Groups[8].Success) into.Add(new Italic(new Run(m.Groups[9].Value)));
                else if (m.Groups[10].Success) into.Add(new Run(m.Groups[11].Value) { TextDecorations = TextDecorations.Strikethrough, Foreground = Dim });
                pos = m.Index + m.Length;
            }
            if (pos < text.Length) into.Add(new Run(text.Substring(pos)));
        }
    }
}
