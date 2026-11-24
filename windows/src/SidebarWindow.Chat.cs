using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace GlassSidebar
{
    // Settings screen: key, provider, models, behaviour. Wires up every other part in InitChat().
    internal sealed partial class SidebarWindow
    {
        public Settings settings = Settings.Load();
        public event Action SettingsChanged;

        ScrollViewer settingsView;
        TextBox modelBox, baseUrlBox, systemBox;
        PasswordBox keyBox;
        TextBlock keyStatus;
        string draftProvider;
        int draftSens;

        static readonly Brush White = Brushes.White;
        static readonly Brush PillOn = Frozen(Color.FromArgb(0x55, 0xFF, 0xFF, 0xFF));
        static readonly Brush PillOff = Frozen(Color.FromArgb(0x14, 0xFF, 0xFF, 0xFF));
        static readonly Brush DimText = Frozen(Color.FromArgb(0x99, 0xFF, 0xFF, 0xFF));

        static Brush Frozen(Color c) { var b = new SolidColorBrush(c); b.Freeze(); return b; }

        bool InSettings { get { return settingsView.Visibility == Visibility.Visible; } }

        void InitChat()
        {
            settingsView = F<ScrollViewer>("SettingsView");
            modelBox = F<TextBox>("ModelBox");
            baseUrlBox = F<TextBox>("BaseUrlBox");
            systemBox = F<TextBox>("SystemBox");
            keyBox = F<PasswordBox>("KeyBox");
            keyStatus = F<TextBlock>("KeyStatus");

            F<Button>("KeyBtn").Click += delegate { ShowSettings(!InSettings); };
            F<Button>("BackBtn").Click += delegate { ShowSettings(false); };
            F<Button>("SaveBtn").Click += delegate { SaveSettings(); };
            F<Button>("ImportBtn").Click += delegate { ImportKeyFromFile(); };
            F<Button>("PasteBtn").Click += delegate
            {
                string k = Settings.ExtractKey(Clipboard.ContainsText() ? Clipboard.GetText() : "");
                if (k == null) { keyStatus.Text = "Clipboard doesn't contain an API key."; return; }
                AcceptKey(k, "Pasted from clipboard.");
            };
            F<Button>("ClearKeyBtn").Click += delegate { keyBox.Password = ""; keyStatus.Text = "Key will be removed when you save."; };
            F<Button>("ProvAnthropic").Click += delegate { SetProvider("anthropic", true); };
            F<Button>("ProvOpenAI").Click += delegate { SetProvider("openai", true); };
            F<Button>("ProvGemini").Click += delegate { SetProvider("gemini", true); };
            F<Button>("ProvGroq").Click += delegate { SetProvider("groq", true); };
            F<Button>("ModelsRefresh").Click += delegate { modelsLoadedFor = null; LoadModels(); };
            modelBox.TextChanged += delegate { HighlightModel(); };
            F<Button>("Sens0").Click += delegate { SetSens(0); };
            F<Button>("Sens1").Click += delegate { SetSens(1); };
            F<Button>("Sens2").Click += delegate { SetSens(2); };

            InitConversation();
            InitComposer();
            InitAppearance();
            InitChatList();
            UpdateStatusText();
        }

        void InputFocus()
        {
            Dispatcher.BeginInvoke(new Action(delegate
            {
                if (InSettings) keyBox.Focus(); else { inputBox.Focus(); Keyboard.Focus(inputBox); }
            }), System.Windows.Threading.DispatcherPriority.Input);
        }

        void UpdateStatusText()
        {
            bool hasKey = !string.IsNullOrEmpty(settings.ApiKey);
            emptyHint.Text = hasKey
                ? "Drop in a file, paste a screenshot, or tap the mic to talk. Flick your cursor into a screen edge any time to summon me."
                : "Add an API key in Settings (the gear above) to get started.";
            modelChipText.Text = hasKey ? settings.Model : "Add API key";
            subtitle.Text = hasKey ? Settings.Label(settings.Provider) + " · " + settings.Model : "Not connected";
        }

        // ---------------- settings ----------------

        void ShowSettings(bool show)
        {
            if (show == InSettings) { if (!show) InputFocus(); return; }
            CloseModelMenu();
            if (show)
            {
                SyncAppearanceControls();
                keyBox.Password = settings.ApiKey;
                modelBox.Text = settings.Model;
                baseUrlBox.Text = settings.BaseUrl;
                systemBox.Text = settings.SystemPrompt;
                keyStatus.Text = string.IsNullOrEmpty(settings.ApiKey) ? "No key saved yet." : "Key saved (encrypted).";
                draftProvider = null;
                SetProvider(settings.Provider, false);
                SetSens(settings.Sensitivity);
            }
            settingsView.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
            chatView.Visibility = show ? Visibility.Collapsed : Visibility.Visible;
            composer.Visibility = show ? Visibility.Collapsed : Visibility.Visible;
            if (show)
            {
                Animate.SlideIn(settingsView, 40);
                var stack = settingsView.Content as StackPanel;
                if (stack != null)
                {
                    int i = 0;
                    foreach (UIElement c in stack.Children)
                    {
                        var card = c as Border;
                        if (card != null) Animate.Rise(card, 40 + 50 * i++, 14);
                    }
                }
            }
            else { Animate.SlideIn(chatView, -30); Animate.Rise((FrameworkElement)composer, 60, 10); }
            InputFocus();
        }

        void SetProvider(string p, bool swapModel, bool keepKey = false)
        {
            if (swapModel && p != draftProvider)
                modelBox.Text = p == "anthropic" ? AiClient.AnthropicDefaultModel : (p == "gemini" ? AiClient.GeminiDefaultModel : "");
            if (p != draftProvider)
            {
                modelsLoadedFor = null;
                // each provider keeps its own key
                if (!keepKey && draftProvider != null)
                {
                    keyBox.Password = settings.KeyFor(p);
                    keyStatus.Text = keyBox.Password.Length > 0 ? "Using your saved " + Settings.Label(p) + " key." : "No " + Settings.Label(p) + " key saved yet.";
                }
            }
            draftProvider = p;
            F<Button>("ProvAnthropic").Background = p == "anthropic" ? PillOn : PillOff;
            F<Button>("ProvGemini").Background = p == "gemini" ? PillOn : PillOff;
            F<Button>("ProvGroq").Background = p == "groq" ? PillOn : PillOff;
            F<Button>("ProvOpenAI").Background = p == "openai" ? PillOn : PillOff;
            F<FrameworkElement>("BaseUrlPanel").Visibility = p == "openai" ? Visibility.Visible : Visibility.Collapsed;
            bool picker = p == "gemini" || p == "groq";
            var panelEl = F<FrameworkElement>("ModelsPanel");
            if (picker && panelEl.Visibility != Visibility.Visible) Animate.Rise(panelEl, 0, 8);
            panelEl.Visibility = picker ? Visibility.Visible : Visibility.Collapsed;
            if (picker)
            {
                F<TextBlock>("ModelsTitle").Text = p == "gemini" ? "Gemini models" : "Groq models";
                if (modelsLoadedFor != p) LoadModels();
            }
        }

        // ---------------- live model picker (Gemini, Groq) ----------------

        string modelsLoadedFor;
        bool modelsLoading;

        async void LoadModels()
        {
            string p = draftProvider;
            string label = p == "gemini" ? "Gemini" : "Groq";
            var status = F<TextBlock>("ModelsStatus");
            var wrap = F<WrapPanel>("ModelsList");
            wrap.Children.Clear();
            modelsLoadedFor = null;
            string key = keyBox.Password.Trim();
            if (key.Length == 0) { status.Text = "Add your " + label + " key above, then hit Refresh to load every model."; return; }
            if (modelsLoading) return;
            modelsLoading = true;
            status.Text = "Loading " + label + " models…";
            Animate.Breathe(status, 0.4, 1, 600);
            try
            {
                var models = await AiClient.ListModelsAsync(p, key);
                if (draftProvider != p) return; // switched provider while loading
                int i = 0;
                foreach (var m in models)
                {
                    var id = m.Key;
                    var b = new Button { Style = (Style)root.FindResource("PillBtn"), Content = m.Value, ToolTip = id, Margin = new Thickness(0, 0, 6, 6), Tag = id };
                    b.Click += delegate { modelBox.Text = id; HighlightModel(); };
                    wrap.Children.Add(b);
                    if (i < 30) Animate.Pop(b, i * 18, 0.9);
                    i++;
                }
                modelsLoadedFor = p;
                if (models.Count > 0 && !models.Any(x => x.Key == modelBox.Text.Trim()) && (p == "groq" || modelBox.Text.Trim().Length == 0))
                    modelBox.Text = models[0].Key;
                status.Text = models.Count + " models available. Tap one to use it.";
                HighlightModel();
            }
            catch (Exception ex) { status.Text = ex.Message; }
            finally { modelsLoading = false; Animate.Stop(status); status.Opacity = 1; }
        }

        void HighlightModel()
        {
            foreach (var c in F<WrapPanel>("ModelsList").Children)
            {
                var b = c as Button;
                if (b != null) b.Background = (b.Tag as string) == modelBox.Text.Trim() ? PillOn : PillOff;
            }
        }

        void SetSens(int s)
        {
            draftSens = s;
            for (int i = 0; i < 3; i++) F<Button>("Sens" + i).Background = i == s ? PillOn : PillOff;
        }

        void AcceptKey(string key, string how)
        {
            keyBox.Password = key;
            string p = Settings.ProviderForKey(key);
            if (p != null && !(p == "openai" && draftProvider == "openai")) SetProvider(p, true, true);
            if (p == "gemini" || p == "groq") { modelsLoadedFor = null; LoadModels(); }
            keyStatus.Text = how + " Looks like " + (p == null ? "an OpenAI-compatible" : "a " + Settings.Label(p)) + " key — hit Save.";
        }

        void ImportKeyFromFile()
        {
            var dlg = new Microsoft.Win32.OpenFileDialog();
            dlg.Title = "Import API key";
            dlg.Filter = "Key files (*.txt;*.env;*.json;*.key)|*.txt;*.env;*.json;*.key|All files (*.*)|*.*";
            suppressDeactivate = true;
            bool? ok;
            try { ok = dlg.ShowDialog(this); }
            finally { suppressDeactivate = false; }
            if (ok != true) return;
            try
            {
                string k = Settings.ExtractKey(File.ReadAllText(dlg.FileName));
                if (k == null) { keyStatus.Text = "Couldn't find an API key in that file."; return; }
                AcceptKey(k, "Imported from " + Path.GetFileName(dlg.FileName) + ".");
            }
            catch (Exception ex) { keyStatus.Text = "Couldn't read file: " + ex.Message; }
            Activate();
        }

        void SaveSettings()
        {
            string model = modelBox.Text.Trim();
            if (model.Length == 0) { keyStatus.Text = "Enter a model name (or pick one from the list)."; modelBox.Focus(); return; }
            settings.Provider = draftProvider ?? "anthropic";
            settings.ApiKey = keyBox.Password.Trim();   // stored under the chosen provider
            settings.Model = model;
            settings.RememberModel(model);
            settings.BaseUrl = baseUrlBox.Text.Trim().Length > 0 ? baseUrlBox.Text.Trim() : "https://api.openai.com/v1";
            settings.SystemPrompt = systemBox.Text;
            settings.Sensitivity = draftSens;
            try { settings.Save(); }
            catch (Exception ex) { keyStatus.Text = "Couldn't save: " + ex.Message; return; }
            var h = SettingsChanged; if (h != null) h();
            UpdateStatusText();
            ShowSettings(false);
            ShowToast("Saved · " + Settings.Label(settings.Provider) + " · " + settings.Model);
        }
    }
}
