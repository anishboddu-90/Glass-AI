using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace GlassSidebar
{
    internal sealed class Settings
    {
        public string Provider = "anthropic";   // anthropic | gemini | groq | openai
        public string Model = "claude-sonnet-5-5";
        public string BaseUrl = "https://api.openai.com/v1";
        public string EncryptedKey = "";
        public int Sensitivity = 1;              // 0 hard flick, 1 normal, 2 light
        public string SystemPrompt = "You are Glass, a sharp, friendly assistant that lives in a sidebar. Be concise and use Markdown when it helps.";
        // glass appearance (applied live)
        public int TintR = 92, TintG = 94, TintB = 100;   // semi-gray
        public double TintStrength = 0.42;
        public double Blur = 9;
        // voice
        public bool SpeakReplies = false;
        public string VoiceName = "";
        public int VoiceRate = 1;                        // -10..10
        // quick model switcher memory
        public List<string> RecentModels = new List<string>();

        [ScriptIgnore] static string Dir { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "GlassSidebar"); } }
        [ScriptIgnore] static string FilePath { get { return Path.Combine(Dir, "settings.json"); } }

        // One key per provider, each encrypted with Windows DPAPI (only your Windows account can decrypt it).
        public Dictionary<string, string> EncryptedKeys = new Dictionary<string, string>();

        [ScriptIgnore]
        public string ApiKey
        {
            get { return KeyFor(Provider); }
            set { SetKey(Provider, value); }
        }

        public string KeyFor(string provider)
        {
            string enc;
            if (EncryptedKeys == null || provider == null || !EncryptedKeys.TryGetValue(provider, out enc) || string.IsNullOrEmpty(enc)) return "";
            try { return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(enc), null, DataProtectionScope.CurrentUser)); }
            catch { return ""; }
        }

        public void SetKey(string provider, string value)
        {
            if (EncryptedKeys == null) EncryptedKeys = new Dictionary<string, string>();
            if (string.IsNullOrEmpty(value)) { EncryptedKeys.Remove(provider); return; }
            EncryptedKeys[provider] = Convert.ToBase64String(ProtectedData.Protect(Encoding.UTF8.GetBytes(value), null, DataProtectionScope.CurrentUser));
        }

        public bool HasKey(string provider) { return KeyFor(provider).Length > 0; }

        public void RememberModel(string model)
        {
            if (string.IsNullOrWhiteSpace(model)) return;
            if (RecentModels == null) RecentModels = new List<string>();
            string tag = Provider + "|" + model;
            RecentModels.Remove(tag);
            RecentModels.Insert(0, tag);
            while (RecentModels.Count > 8) RecentModels.RemoveAt(RecentModels.Count - 1);
        }

        public static Settings Load()
        {
            try
            {
                if (File.Exists(FilePath))
                {
                    var s = new JavaScriptSerializer().Deserialize<Settings>(File.ReadAllText(FilePath)) ?? new Settings();
                    if (s.RecentModels == null) s.RecentModels = new List<string>();
                    if (s.EncryptedKeys == null) s.EncryptedKeys = new Dictionary<string, string>();
                    // older versions stored a single key: give it to the current provider
                    if (!string.IsNullOrEmpty(s.EncryptedKey) && !s.EncryptedKeys.ContainsKey(s.Provider))
                        s.EncryptedKeys[s.Provider] = s.EncryptedKey;
                    s.EncryptedKey = "";
                    return s;
                }
            }
            catch { }
            return new Settings();
        }

        public void Save()
        {
            Directory.CreateDirectory(Dir);
            File.WriteAllText(FilePath, new JavaScriptSerializer().Serialize(this));
        }

        // Pulls a key out of pasted text, a .txt, a .env, or a .json file.
        public static string ExtractKey(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return null;
            var m = Regex.Match(text, @"sk-ant-[A-Za-z0-9_\-]{20,}");
            if (m.Success) return m.Value;
            m = Regex.Match(text, @"AIza[0-9A-Za-z_\-]{30,}");   // Google / Gemini keys
            if (m.Success) return m.Value;
            m = Regex.Match(text, @"gsk_[0-9A-Za-z]{20,}");      // Groq keys
            if (m.Success) return m.Value;
            m = Regex.Match(text, @"(?:ANTHROPIC|OPENAI|OPENROUTER|GROQ|GEMINI|GOOGLE)?_?API_KEY\s*[=:]\s*[""']?([A-Za-z0-9_\-\.]{16,})");
            if (m.Success) return m.Groups[1].Value;
            m = Regex.Match(text, @"sk-[A-Za-z0-9_\-]{20,}");
            if (m.Success) return m.Value;
            string t = text.Trim();
            if (t.Length >= 16 && !t.Contains(" ") && !t.Contains("\n")) return t;
            return null;
        }

        public static string ProviderForKey(string key)
        {
            if (key.StartsWith("sk-ant-")) return "anthropic";
            if (key.StartsWith("AIza")) return "gemini";
            if (key.StartsWith("gsk_")) return "groq";
            if (key.StartsWith("sk-")) return "openai";
            return null;
        }

        public static string Label(string p)
        {
            return p == "anthropic" ? "Claude" : p == "gemini" ? "Gemini" : p == "groq" ? "Groq" : p == "openai" ? "OpenAI" : "Assistant";
        }
    }

    // Something attached to a message: an image, a PDF, or a text/code file.
    internal sealed class Attachment
    {
        public string Name = "";
        public string Kind = "";        // image | pdf | text
        public string MediaType = "";   // image/jpeg, image/png, application/pdf, text/plain
        public string Data = "";        // base64 for image/pdf
        public string Text = "";        // contents for text files
        public long Bytes;
    }

    internal sealed class ChatMessage
    {
        public string Role; public string Content;
        public List<Attachment> Attachments = new List<Attachment>();
        public string Provider = "", Model = "";
        public string Error;
        public long Time = DateTime.UtcNow.Ticks;
        public ChatMessage() { }   // for JSON loading
        public ChatMessage(string role, string content) { Role = role; Content = content; }
    }

    internal static class AiClient
    {
        static readonly HttpClient http;
        public const string GeminiOpenAiBase = "https://generativelanguage.googleapis.com/v1beta/openai";
        public const string GeminiDefaultModel = "gemini-4-hydrogen";
        public const string GroqBase = "https://api.groq.com/openai/v1";
        public const string AnthropicDefaultModel = "claude-sonnet-5-5";

        static AiClient()
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            http = new HttpClient();
            http.Timeout = TimeSpan.FromMinutes(5);
        }

        static bool HasMedia(ChatMessage m) { return m.Attachments != null && m.Attachments.Count > 0; }

        // text files are folded into the prompt so every provider can read them
        static string TextWithFiles(ChatMessage m)
        {
            var sb = new StringBuilder();
            if (m.Attachments != null)
                foreach (var a in m.Attachments.Where(x => x.Kind == "text"))
                    sb.Append("File: ").Append(a.Name).Append("\n```\n").Append(a.Text).Append("\n```\n\n");
            sb.Append(m.Content ?? "");
            return sb.ToString();
        }

        static object AnthropicContent(ChatMessage m)
        {
            if (!HasMedia(m)) return m.Content ?? "";
            var blocks = new List<object>();
            foreach (var a in m.Attachments)
            {
                if (a.Kind == "image")
                    blocks.Add(new Dictionary<string, object> { { "type", "image" },
                        { "source", new Dictionary<string, object> { { "type", "base64" }, { "media_type", a.MediaType }, { "data", a.Data } } } });
                else if (a.Kind == "pdf")
                    blocks.Add(new Dictionary<string, object> { { "type", "document" },
                        { "source", new Dictionary<string, object> { { "type", "base64" }, { "media_type", "application/pdf" }, { "data", a.Data } } } });
            }
            string text = TextWithFiles(m);
            if (text.Trim().Length == 0) text = "(see attachment)";
            blocks.Add(new Dictionary<string, object> { { "type", "text" }, { "text", text } });
            return blocks;
        }

        static object OpenAiContent(ChatMessage m, string provider)
        {
            if (!HasMedia(m)) return m.Content ?? "";
            var parts = new List<object>();
            string text = TextWithFiles(m);
            foreach (var a in m.Attachments.Where(x => x.Kind == "pdf"))
            {
                if (provider == "openai")
                    parts.Add(new Dictionary<string, object> { { "type", "file" },
                        { "file", new Dictionary<string, object> { { "filename", a.Name }, { "file_data", "data:application/pdf;base64," + a.Data } } } });
                else
                    text = "[A PDF named " + a.Name + " was attached, but this provider can't read PDFs directly.]\n\n" + text;
            }
            if (text.Trim().Length == 0) text = "(see attachment)";
            parts.Add(new Dictionary<string, object> { { "type", "text" }, { "text", text } });
            foreach (var a in m.Attachments.Where(x => x.Kind == "image"))
                parts.Add(new Dictionary<string, object> { { "type", "image_url" },
                    { "image_url", new Dictionary<string, object> { { "url", "data:" + a.MediaType + ";base64," + a.Data } } } });
            return parts;
        }

        public static async Task StreamAsync(Settings s, List<ChatMessage> history, Action<string> onDelta, CancellationToken ct)
        {
            string key = s.ApiKey;
            if (string.IsNullOrEmpty(key)) throw new Exception("No API key yet. Open Settings to add one.");
            var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            HttpRequestMessage req;
            bool anthropic = s.Provider == "anthropic";

            var msgs = new List<Dictionary<string, object>>();
            if (!anthropic && !string.IsNullOrEmpty(s.SystemPrompt))
                msgs.Add(new Dictionary<string, object> { { "role", "system" }, { "content", s.SystemPrompt } });
            foreach (var m in history)
            {
                if (m.Role == "assistant" && string.IsNullOrEmpty(m.Content)) continue;
                msgs.Add(new Dictionary<string, object> { { "role", m.Role },
                    { "content", anthropic ? AnthropicContent(m) : OpenAiContent(m, s.Provider) } });
            }

            if (anthropic)
            {
                var body = new Dictionary<string, object> {
                    { "model", s.Model }, { "max_tokens", 8192 }, { "stream", true }, { "messages", msgs } };
                if (!string.IsNullOrEmpty(s.SystemPrompt)) body["system"] = s.SystemPrompt;
                req = new HttpRequestMessage(HttpMethod.Post, "https://api.anthropic.com/v1/messages");
                req.Headers.Add("x-api-key", key);
                req.Headers.Add("anthropic-version", "2023-06-01");
                req.Content = new StringContent(json.Serialize(body), Encoding.UTF8, "application/json");
            }
            else
            {
                string baseUrl = s.Provider == "gemini" ? GeminiOpenAiBase : (s.Provider == "groq" ? GroqBase : s.BaseUrl);
                var body = new Dictionary<string, object> { { "model", s.Model }, { "stream", true }, { "messages", msgs } };
                req = new HttpRequestMessage(HttpMethod.Post, baseUrl.TrimEnd('/') + "/chat/completions");
                req.Headers.Add("Authorization", "Bearer " + key);
                req.Content = new StringContent(json.Serialize(body), Encoding.UTF8, "application/json");
            }

            using (var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct))
            {
                if (!resp.IsSuccessStatusCode)
                {
                    string err = await resp.Content.ReadAsStringAsync();
                    throw new Exception("API error " + (int)resp.StatusCode + ": " + ErrorText(err));
                }
                using (var stream = await resp.Content.ReadAsStreamAsync())
                using (var reader = new StreamReader(stream, Encoding.UTF8))
                {
                    while (!reader.EndOfStream)
                    {
                        ct.ThrowIfCancellationRequested();
                        string line = await reader.ReadLineAsync();
                        if (line == null) break;
                        if (!line.StartsWith("data:")) continue;
                        string data = line.Substring(5).Trim();
                        if (data == "[DONE]") break;
                        Dictionary<string, object> evt;
                        try { evt = json.Deserialize<Dictionary<string, object>>(data); } catch { continue; }
                        string delta = anthropic ? AnthropicDelta(evt) : OpenAiDelta(evt);
                        if (!string.IsNullOrEmpty(delta)) onDelta(delta);
                    }
                }
            }
        }

        // One-shot, non-streaming call used for chat titles.
        public static async Task<string> QuickAsync(Settings s, string prompt)
        {
            var sb = new StringBuilder();
            var tmp = new Settings { Provider = s.Provider, Model = s.Model, BaseUrl = s.BaseUrl, EncryptedKeys = s.EncryptedKeys, SystemPrompt = "" };
            var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            await StreamAsync(tmp, new List<ChatMessage> { new ChatMessage("user", prompt) }, d => sb.Append(d), cts.Token);
            return sb.ToString();
        }

        static string AnthropicDelta(Dictionary<string, object> e)
        {
            object type; e.TryGetValue("type", out type);
            if ((type as string) == "error") throw new Exception(ErrorText(new JavaScriptSerializer().Serialize(e)));
            if ((type as string) != "content_block_delta") return null;
            var d = e["delta"] as Dictionary<string, object>;
            object text;
            return d != null && d.TryGetValue("text", out text) ? text as string : null;
        }

        static string OpenAiDelta(Dictionary<string, object> e)
        {
            object choices;
            if (!e.TryGetValue("choices", out choices)) return null;
            var arr = choices as object[] ?? (choices as System.Collections.ArrayList ?? new System.Collections.ArrayList()).ToArray();
            if (arr.Length == 0) return null;
            var c = arr[0] as Dictionary<string, object>;
            object delta;
            if (c == null || !c.TryGetValue("delta", out delta)) return null;
            var d = delta as Dictionary<string, object>;
            object content;
            return d != null && d.TryGetValue("content", out content) ? content as string : null;
        }

        // ---------------- live model lists ----------------

        public static async Task<List<KeyValuePair<string, string>>> ListModelsAsync(string provider, string key)
        {
            if (provider == "gemini") return await ListGeminiModelsAsync(key);
            if (provider == "groq") return await ListGroqModelsAsync(key);
            return new List<KeyValuePair<string, string>>();
        }

        // Every Gemini model this key can chat with, straight from Google.
        public static async Task<List<KeyValuePair<string, string>>> ListGeminiModelsAsync(string key)
        {
            var result = new List<KeyValuePair<string, string>>();
            var json = new JavaScriptSerializer();
            string pageToken = null;
            do
            {
                string url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000" +
                             (pageToken != null ? "&pageToken=" + Uri.EscapeDataString(pageToken) : "");
                var req = new HttpRequestMessage(HttpMethod.Get, url);
                req.Headers.Add("x-goog-api-key", key);
                using (var resp = await http.SendAsync(req))
                {
                    string raw = await resp.Content.ReadAsStringAsync();
                    if (!resp.IsSuccessStatusCode) throw new Exception("Couldn't list models (" + (int)resp.StatusCode + "): " + ErrorText(raw));
                    var page = json.Deserialize<Dictionary<string, object>>(raw);
                    object models;
                    if (page.TryGetValue("models", out models))
                        foreach (var o in (System.Collections.IEnumerable)models)
                        {
                            var mdl = o as Dictionary<string, object>;
                            if (mdl == null) continue;
                            string id = (mdl["name"] as string ?? "").Replace("models/", "");
                            object methods, display;
                            bool chat = mdl.TryGetValue("supportedGenerationMethods", out methods) &&
                                        ((System.Collections.IEnumerable)methods).Cast<object>().Contains("generateContent");
                            if (!chat || !id.StartsWith("gemini")) continue;
                            mdl.TryGetValue("displayName", out display);
                            result.Add(new KeyValuePair<string, string>(id, (display as string) ?? id));
                        }
                    object next;
                    pageToken = page.TryGetValue("nextPageToken", out next) ? next as string : null;
                    if (pageToken == "") pageToken = null;
                }
            } while (pageToken != null);
            result.Sort((a, b) => string.CompareOrdinal(b.Key, a.Key));
            return result;
        }

        // Every chat model on this Groq account (skips speech-to-text, TTS and safety-guard models).
        public static async Task<List<KeyValuePair<string, string>>> ListGroqModelsAsync(string key)
        {
            var result = new List<KeyValuePair<string, string>>();
            var req = new HttpRequestMessage(HttpMethod.Get, GroqBase + "/models");
            req.Headers.Add("Authorization", "Bearer " + key);
            using (var resp = await http.SendAsync(req))
            {
                string raw = await resp.Content.ReadAsStringAsync();
                if (!resp.IsSuccessStatusCode) throw new Exception("Couldn't list models (" + (int)resp.StatusCode + "): " + ErrorText(raw));
                var page = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(raw);
                object data;
                if (page.TryGetValue("data", out data))
                    foreach (var o in (System.Collections.IEnumerable)data)
                    {
                        var mdl = o as Dictionary<string, object>;
                        if (mdl == null) continue;
                        string id = mdl["id"] as string ?? "";
                        object active;
                        if (mdl.TryGetValue("active", out active) && active is bool && !(bool)active) continue;
                        string low = id.ToLowerInvariant();
                        if (low.Contains("whisper") || low.Contains("tts") || low.Contains("guard") || low.Contains("orpheus")) continue;
                        result.Add(new KeyValuePair<string, string>(id, id));
                    }
            }
            result.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));
            return result;
        }

        public static string ErrorText(string raw)
        {
            var m = Regex.Match(raw ?? "", "\"message\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            return m.Success ? Regex.Unescape(m.Groups[1].Value) : (raw ?? "").Length > 300 ? raw.Substring(0, 300) : raw;
        }
    }
}
