using System;
using System.Linq;
using System.Speech.Recognition;
using System.Speech.Synthesis;
using System.Text.RegularExpressions;

namespace GlassSidebar
{
    // Voice in (Windows offline dictation) and voice out (Windows text-to-speech). No extra API keys.
    internal sealed class Voice : IDisposable
    {
        SpeechRecognitionEngine rec;
        readonly SpeechSynthesizer tts = new SpeechSynthesizer();

        public event Action<string> Partial;     // live words while you talk
        public event Action<string> Final;       // a finished phrase
        public event Action<double> Level;       // mic level 0..1 (for the animation)
        public event Action Stopped;
        public event Action<bool> SpeakingChanged;

        public bool Listening { get; private set; }
        public bool Speaking { get; private set; }

        public Voice()
        {
            tts.SetOutputToDefaultAudioDevice();
            tts.SpeakStarted += delegate { Speaking = true; var h = SpeakingChanged; if (h != null) h(true); };
            tts.SpeakCompleted += delegate { Speaking = false; var h = SpeakingChanged; if (h != null) h(false); };
        }

        public static string[] VoiceNames()
        {
            try { return new SpeechSynthesizer().GetInstalledVoices().Where(v => v.Enabled).Select(v => v.VoiceInfo.Name).ToArray(); }
            catch { return new string[0]; }
        }

        public void Start()
        {
            if (Listening) return;
            if (rec == null)
            {
                var info = SpeechRecognitionEngine.InstalledRecognizers();
                if (info.Count == 0) throw new Exception("No speech recognizer is installed. Add one in Windows Settings › Time & language › Speech.");
                var culture = System.Globalization.CultureInfo.CurrentUICulture;
                var pick = info.FirstOrDefault(r => r.Culture.Name == culture.Name)
                        ?? info.FirstOrDefault(r => r.Culture.TwoLetterISOLanguageName == culture.TwoLetterISOLanguageName)
                        ?? info[0];
                rec = new SpeechRecognitionEngine(pick);
                rec.LoadGrammar(new DictationGrammar());
                rec.SpeechHypothesized += (s, e) => { var h = Partial; if (h != null) h(e.Result.Text); };
                rec.SpeechRecognized += (s, e) =>
                {
                    if (e.Result.Confidence < 0.2f) return;
                    var h = Final; if (h != null) h(e.Result.Text);
                };
                rec.AudioLevelUpdated += (s, e) => { var h = Level; if (h != null) h(Math.Min(1.0, e.AudioLevel / 60.0)); };
                rec.RecognizeCompleted += delegate { Listening = false; var h = Stopped; if (h != null) h(); };
            }
            rec.SetInputToDefaultAudioDevice();
            rec.RecognizeAsync(RecognizeMode.Multiple);
            Listening = true;
        }

        public void Stop()
        {
            if (rec != null && Listening) rec.RecognizeAsyncStop();
        }

        public void Speak(string markdown, string voiceName, int rate)
        {
            StopSpeaking();
            try { if (!string.IsNullOrEmpty(voiceName)) tts.SelectVoice(voiceName); } catch { }
            tts.Rate = Math.Max(-10, Math.Min(10, rate));
            string text = Plain(markdown);
            if (text.Length > 0) tts.SpeakAsync(text);
        }

        public void StopSpeaking() { tts.SpeakAsyncCancelAll(); }

        // Markdown -> something pleasant to listen to
        static string Plain(string md)
        {
            string t = md ?? "";
            t = Regex.Replace(t, @"```[\s\S]*?```", " (code block) ");
            t = Regex.Replace(t, @"`([^`]+)`", "$1");
            t = Regex.Replace(t, @"!\[[^\]]*\]\([^)]*\)", "");
            t = Regex.Replace(t, @"\[([^\]]+)\]\([^)]*\)", "$1");
            t = Regex.Replace(t, @"[*_#>~|]+", "");
            t = Regex.Replace(t, @"^\s*[-+]\s+", "", RegexOptions.Multiline);
            return Regex.Replace(t, @"\s+", " ").Trim();
        }

        public void Dispose()
        {
            try { if (rec != null) rec.Dispose(); } catch { }
            try { tts.Dispose(); } catch { }
        }
    }
}
