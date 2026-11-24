import AppKit
import AVFoundation
import SwiftUI
import UniformTypeIdentifiers

struct SettingsView: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @State private var keyText = ""
    @State private var keyStatus = ""
    @State private var models: [String: [(id: String, name: String)]] = [:]
    @State private var loadingModels = false
    @State private var modelError = ""

    static let tints: [(String, String)] = [("Graphite", "#5C5E64"), ("Clear", "#FFFFFF"), ("Midnight", "#1C2440"), ("Ocean", "#2A6FB0"),
                                           ("Mint", "#3BB59A"), ("Violet", "#7A5CFF"), ("Rose", "#E0607E"), ("Amber", "#D99A3A")]

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 14) {
                card("API key", icon: "key.fill", delay: 0) { keyCard }
                card("Model", icon: "sparkles", delay: 0.04) { modelCard }
                card("Glass", icon: "drop.fill", delay: 0.08) { glassCard }
                card("Voice", icon: "waveform", delay: 0.12) { voiceCard }
                card("Edge flick", icon: "cursorarrow.motionlines", delay: 0.16) { flickCard }
                card("Instructions", icon: "text.quote", delay: 0.2) { promptCard }
                Text("Glass · ⌃⌥Space toggles from anywhere · Esc closes")
                    .font(.system(size: 10.5)).foregroundStyle(UI.faint).frame(maxWidth: .infinity).appear(0.26)
            }
            .padding(16)
            .frame(maxWidth: pc.full ? 640 : .infinity)
            .frame(maxWidth: .infinity)
        }
        .onAppear { keyText = ""; refreshStatus(); loadModels() }
        .onChange(of: s.provider) { _, _ in keyText = ""; refreshStatus(); loadModels() }
    }

    private func card<C: View>(_ title: String, icon: String, delay: Double, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon).font(.system(size: 12, weight: .semibold)).foregroundStyle(UI.dim)
            c()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .chip(16)
        .appear(delay, y: 16)
    }

    // MARK: key

    private var keyCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                ForEach(Settings.providers, id: \.self) { p in
                    PillButton(title: Settings.label(p), symbol: s.hasKey(p) ? "checkmark.circle.fill" : nil, selected: s.provider == p) {
                        withAnimation(UI.spring) { switchProvider(p) }
                    }
                }
            }
            HStack(spacing: 6) {
                SecureField("", text: $keyText, prompt: Text(s.hasKey(s.provider) ? "•••••••• saved in Keychain" : placeholder).foregroundColor(UI.faint))
                    .textFieldStyle(.plain).font(.system(size: 13, design: .monospaced))
                    .padding(.horizontal, 10).frame(height: 32).chip(10)
                    .onSubmit { accept(keyText) }
                IconButton(symbol: "doc.on.clipboard", help: "Paste key", size: 30) { accept(NSPasteboard.general.string(forType: .string) ?? "") }
                IconButton(symbol: "folder", help: "Import from a .txt / .env / .json file", size: 30) { importFile() }
                if s.hasKey(s.provider) {
                    IconButton(symbol: "trash", help: "Remove key", size: 30) { s.setKey("", for: s.provider); refreshStatus() }
                }
            }
            if !keyText.isEmpty {
                PillButton(title: "Save key", symbol: "lock.fill", selected: true) { accept(keyText) }.transition(.scale.combined(with: .opacity))
            }
            Text(keyStatus).font(.system(size: 11)).foregroundStyle(UI.faint).id(keyStatus).transition(.opacity)
        }
        .animation(UI.spring, value: keyText.isEmpty)
    }

    private var placeholder: String {
        switch s.provider {
        case "anthropic": return "sk-ant-…"
        case "gemini": return "AIza…"
        case "groq": return "gsk_…"
        default: return "sk-…"
        }
    }

    private func refreshStatus() {
        let where_ = s.provider == "anthropic" ? "console.anthropic.com" : s.provider == "gemini" ? "aistudio.google.com" :
                     s.provider == "groq" ? "console.groq.com" : "your provider's dashboard"
        keyStatus = s.hasKey(s.provider) ? "Stored securely in your macOS Keychain." : "Get a key at \(where_). Keys never leave this Mac except to call the API."
    }

    private func switchProvider(_ p: String) {
        guard p != s.provider else { return }
        s.provider = p
        switch p {
        case "anthropic": if !AI.claudeModels.contains(s.model) { s.model = AI.anthropicDefault }
        case "gemini": if !s.model.hasPrefix("gemini") { s.model = AI.geminiDefault }
        case "groq": s.model = "llama-3.3-70b-versatile"
        default: s.model = "gpt-4.1"
        }
    }

    private func accept(_ raw: String) {
        guard let k = Settings.extractKey(raw) else { keyStatus = "That doesn't look like an API key."; return }
        if let p = Settings.providerFor(key: k), p != s.provider { switchProvider(p) }
        s.setKey(k, for: s.provider)
        keyText = ""
        withAnimation(UI.soft) { keyStatus = "Saved \(Settings.label(s.provider)) key to Keychain ✓" }
        pc.show(toast: "\(Settings.label(s.provider)) is ready")
        loadModels()
    }

    private func importFile() {
        pc.holdOpen = true
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText, .json, .data]
        panel.level = .modalPanel
        NSApp.activate(ignoringOtherApps: true)
        panel.begin { r in
            MainActor.assumeIsolated {
                pc.holdOpen = false
                guard r == .OK, let u = panel.url, let t = try? String(contentsOf: u, encoding: .utf8) else { return }
                accept(t)
            }
        }
    }

    // MARK: model

    private var modelCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            let list: [(id: String, name: String)] = s.provider == "anthropic" ? AI.claudeModels.map { (id: $0, name: $0) } : (models[s.provider] ?? [])
            if !list.isEmpty {
                ScrollView {
                    VStack(spacing: 1) {
                        ForEach(list, id: \.id) { m in
                            HoverRow(selected: s.model == m.id, action: { s.model = m.id; s.rememberModel(m.id) }) { _ in
                                HStack {
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(m.name).font(.system(size: 12.5)).lineLimit(1)
                                        if m.name != m.id { Text(m.id).font(.system(size: 10.5)).foregroundStyle(UI.faint).lineLimit(1) }
                                    }
                                    Spacer()
                                    if s.model == m.id { Image(systemName: "checkmark").font(.system(size: 10, weight: .bold)).foregroundStyle(UI.accent) }
                                }
                            }
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
            if loadingModels { HStack { ProgressView().controlSize(.small); Text("Loading models…").font(.system(size: 11)).foregroundStyle(UI.faint) } }
            if !modelError.isEmpty { Text(modelError).font(.system(size: 11)).foregroundStyle(Color(hex: "#FFB4A8")!) }
            TextField("", text: $s.model, prompt: Text("Model ID").foregroundColor(UI.faint))
                .textFieldStyle(.plain).font(.system(size: 12.5, design: .monospaced))
                .padding(.horizontal, 10).frame(height: 30).chip(10)
            if s.provider == "openai" {
                TextField("", text: $s.baseURL, prompt: Text("Base URL (OpenAI, OpenRouter, Ollama, LM Studio…)").foregroundColor(UI.faint))
                    .textFieldStyle(.plain).font(.system(size: 12.5, design: .monospaced))
                    .padding(.horizontal, 10).frame(height: 30).chip(10)
            }
        }
    }

    private func loadModels() {
        let p = s.provider
        guard p == "gemini" || p == "groq", s.hasKey(p) else { modelError = ""; return }
        loadingModels = true; modelError = ""
        let key = s.key(for: p)
        Task {
            do {
                let r = try await AI.models(provider: p, key: key)
                withAnimation(UI.soft) { models[p] = r }
            } catch {
                modelError = error.localizedDescription
            }
            loadingModels = false
        }
    }

    // MARK: glass

    private var glassCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                ForEach(SettingsView.tints, id: \.1) { name, hex in
                    Swatch(hex: hex, selected: s.tintHex.uppercased() == hex.uppercased()) { withAnimation(UI.spring) { s.tintHex = hex } }
                        .help(name)
                }
                ColorPicker("", selection: Binding(get: { s.tintColor }, set: { s.tintHex = $0.hex }), supportsOpacity: false)
                    .labelsHidden().frame(width: 26)
            }
            slider("Tint", value: $s.tintStrength, range: 0...0.85, text: "\(Int(s.tintStrength * 100))%")
            HStack(spacing: 6) {
                Text("Style").font(.system(size: 12)).foregroundStyle(UI.dim).frame(width: 60, alignment: .leading)
                ForEach([("clear", "Clear"), ("regular", "Liquid"), ("frosted", "Frosted")], id: \.0) { id, name in
                    PillButton(title: name, selected: s.glassStyle == id) { withAnimation(UI.spring) { s.glassStyle = id } }
                }
            }
            Button("Reset to semi-gray") {
                withAnimation(UI.spring) { s.tintHex = Settings.defaultTint; s.tintStrength = Settings.defaultStrength; s.glassStyle = "regular" }
            }
            .buttonStyle(.plain).font(.system(size: 11.5, weight: .medium)).foregroundStyle(UI.dim)
        }
    }

    private func slider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, text: String) -> some View {
        HStack(spacing: 10) {
            Text(title).font(.system(size: 12)).foregroundStyle(UI.dim).frame(width: 60, alignment: .leading)
            Slider(value: value, in: range).controlSize(.small).tint(.white)
            Text(text).font(.system(size: 11, design: .monospaced)).foregroundStyle(UI.faint).frame(width: 40, alignment: .trailing)
        }
    }

    // MARK: voice

    private var voiceCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle(isOn: $s.speakReplies) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Read replies aloud").font(.system(size: 12.5))
                    Text("Voice mode (⌘⇧V) always talks back").font(.system(size: 10.5)).foregroundStyle(UI.faint)
                }
            }
            .toggleStyle(.switch).controlSize(.small)
            HStack {
                Text("Voice").font(.system(size: 12)).foregroundStyle(UI.dim).frame(width: 60, alignment: .leading)
                Picker("", selection: $s.voiceID) {
                    Text("System default").tag("")
                    ForEach(Voice.voices, id: \.identifier) { v in
                        Text("\(v.name)\(v.quality == .premium ? " (Premium)" : v.quality == .enhanced ? " (Enhanced)" : "")").tag(v.identifier)
                    }
                }
                .labelsHidden()
                IconButton(symbol: "play.fill", help: "Preview", size: 26) { Voice.shared.speak("Hi, I'm Glass. This is how I sound.") }
            }
            Text("Dictation runs on-device when your Mac supports it. Download better voices in System Settings → Accessibility → Spoken Content.")
                .font(.system(size: 10.5)).foregroundStyle(UI.faint).fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: flick

    private var flickCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                ForEach([(0, "Firm"), (1, "Normal"), (2, "Light")], id: \.0) { k, name in
                    PillButton(title: name, selected: s.sensitivity == k) { withAnimation(UI.spring) { s.sensitivity = k } }
                }
            }
            Text("Flick your cursor fast into the left or right edge of any screen to open Glass on that side.")
                .font(.system(size: 10.5)).foregroundStyle(UI.faint).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var promptCard: some View {
        TextEditor(text: $s.systemPrompt)
            .font(.system(size: 12.5))
            .scrollContentBackground(.hidden)
            .frame(height: 90)
            .padding(6).chip(10)
    }
}

struct Swatch: View {
    var hex: String
    var selected: Bool
    var action: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: action) {
            Circle().fill(Color(hex: hex)!)
                .frame(width: 22, height: 22)
                .overlay(Circle().strokeBorder(Color.white.opacity(selected ? 0.95 : 0.3), lineWidth: selected ? 2 : 1))
                .padding(2)
                .overlay(Circle().strokeBorder(Color.white.opacity(selected ? 0.35 : 0), lineWidth: 1))
                .scaleEffect(selected ? 1.12 : hover ? 1.08 : 1)
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
    }
}

extension Color {
    var hex: String {
        let c = NSColor(self).usingColorSpace(.sRGB) ?? .gray
        return String(format: "#%02X%02X%02X", Int(c.redComponent * 255), Int(c.greenComponent * 255), Int(c.blueComponent * 255))
    }
}
