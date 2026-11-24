using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;

namespace GlassSidebar
{
    internal sealed class ChatSession
    {
        public string Id = Guid.NewGuid().ToString("N");
        public string Title = "New chat";
        public bool SmartTitled;
        public bool Pinned;
        public long Updated = DateTime.UtcNow.Ticks;
        public string Provider = "";
        public string Model = "";
        public List<ChatMessage> Messages = new List<ChatMessage>();
    }

    // Chats are plain JSON files in %APPDATA%\GlassSidebar\chats, one per conversation.
    internal static class ChatStore
    {
        static string Dir
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "GlassSidebar", "chats"); }
        }

        static JavaScriptSerializer Json() { return new JavaScriptSerializer { MaxJsonLength = int.MaxValue }; }

        public static List<ChatSession> LoadAll()
        {
            var list = new List<ChatSession>();
            try
            {
                if (!Directory.Exists(Dir)) return list;
                foreach (var f in Directory.GetFiles(Dir, "*.json"))
                {
                    try
                    {
                        var s = Json().Deserialize<ChatSession>(File.ReadAllText(f));
                        if (s == null || s.Messages == null || s.Messages.Count == 0) continue;
                        foreach (var m in s.Messages) if (m.Attachments == null) m.Attachments = new List<Attachment>();
                        list.Add(s);
                    }
                    catch { } // skip a corrupt file rather than losing everything
                }
            }
            catch { }
            return Sort(list);
        }

        public static List<ChatSession> Sort(IEnumerable<ChatSession> chats)
        {
            return chats.OrderByDescending(c => c.Pinned).ThenByDescending(c => c.Updated).ToList();
        }

        public static void Save(ChatSession s, bool touch = true)
        {
            try
            {
                Directory.CreateDirectory(Dir);
                if (touch) s.Updated = DateTime.UtcNow.Ticks;
                string path = Path.Combine(Dir, s.Id + ".json");
                string tmp = path + ".tmp";
                File.WriteAllText(tmp, Json().Serialize(s));
                if (File.Exists(path)) File.Delete(path);
                File.Move(tmp, path);
            }
            catch { }
        }

        public static void Delete(string id)
        {
            try { File.Delete(Path.Combine(Dir, id + ".json")); } catch { }
        }

        public static string Export(ChatSession s)
        {
            var sb = new System.Text.StringBuilder();
            sb.Append("# ").Append(s.Title).Append("\n\n");
            foreach (var m in s.Messages)
            {
                sb.Append(m.Role == "user" ? "**You**" : "**" + Settings.Label(m.Provider) + "**").Append("\n\n");
                foreach (var a in m.Attachments ?? new List<Attachment>()) sb.Append("> 📎 ").Append(a.Name).Append("\n");
                sb.Append(m.Content).Append("\n\n---\n\n");
            }
            return sb.ToString();
        }

        public static string MakeTitle(string firstMessage)
        {
            string t = (firstMessage ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
            while (t.Contains("  ")) t = t.Replace("  ", " ");
            if (t.Length == 0) return "New chat";
            return t.Length > 42 ? t.Substring(0, 40).TrimEnd() + "…" : t;
        }

        public static string RelativeTime(long ticks)
        {
            var span = DateTime.UtcNow - new DateTime(ticks, DateTimeKind.Utc);
            if (span.TotalMinutes < 1) return "Just now";
            if (span.TotalHours < 1) return (int)span.TotalMinutes + "m ago";
            if (span.TotalDays < 1) return (int)span.TotalHours + "h ago";
            if (span.TotalDays < 2) return "Yesterday";
            if (span.TotalDays < 7) return (int)span.TotalDays + "d ago";
            return new DateTime(ticks, DateTimeKind.Utc).ToLocalTime().ToString("MMM d");
        }

        // Groups for the chat list: Pinned / Today / Yesterday / Previous 7 days / Older
        public static string Bucket(ChatSession c)
        {
            if (c.Pinned) return "Pinned";
            var local = new DateTime(c.Updated, DateTimeKind.Utc).ToLocalTime().Date;
            var today = DateTime.Now.Date;
            if (local == today) return "Today";
            if (local == today.AddDays(-1)) return "Yesterday";
            if (local > today.AddDays(-7)) return "Previous 7 days";
            return "Older";
        }
    }
}
