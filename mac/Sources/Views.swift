import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Root

struct RootView: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @EnvironmentObject var chat: ChatModel
    @EnvironmentObject var voice: Voice
    @State private var dropping = false

    private var glow: Color? {
        if voice.listening { return Color(hex: "#FF5A5A") }
        if chat.isStreaming { return Color(hex: "#A98BFF") }
        if voice.speaking { return Color(hex: "#6BFFC8") }
        return nil
    }

    var body: some View {
        GeometryReader { geo in
            let m = PanelController.margin
            let w = pc.full ? geo.size.width - m * 2 : PanelController.width
            let h = geo.size.height - m * 2
            let anchor: UnitPoint = pc.side < 0 ? .leading : .trailing
            panel
                .frame(width: w, height: h)
                .shadow(color: .black.opacity(pc.visible ? 0.38 : 0), radius: 34, y: 14)
                // liquid entrance: slides from the edge, squashed, then springs into shape
                .scaleEffect(x: pc.visible ? 1 : 0.82, y: pc.visible ? 1 : 1.04, anchor: anchor)
                .offset(x: pc.visible ? 0 : pc.side * (w * 0.6 + 80))
                .blur(radius: pc.visible ? 0 : 14)
                .opacity(pc.visible ? 1 : 0)
                .padding(m)
                .frame(width: geo.size.width, height: geo.size.height, alignment: pc.side < 0 ? .leading : .trailing)
        }
        .ignoresSafeArea()
    }

    private var shape: RoundedRectangle { RoundedRectangle(cornerRadius: UI.radius, style: .continuous) }

    private var panel: some View {
        ZStack {
            GlassSurface(shape: shape, tint: s.tintColor, strength: s.tintStrength, style: s.glassStyle, glow: glow)

            HStack(spacing: 0) {
                if pc.full {
                    ChatsSidebar()
                        .frame(width: 272)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                    Rectangle().fill(UI.hair).frame(width: 1).transition(.opacity)
                }
                VStack(spacing: 0) {
                    Header()
                    Rectangle().fill(UI.hair).frame(height: 1).opacity(chat.isEmpty && pc.page == .chat ? 0 : 1)
                    ZStack {
                        if pc.page == .settings {
                            SettingsView()
                                .transition(.asymmetric(insertion: .move(edge: .trailing).combined(with: .opacity),
                                                        removal: .move(edge: .trailing).combined(with: .opacity)))
                        } else {
                            ChatPane()
                                .transition(.asymmetric(insertion: .move(edge: .leading).combined(with: .opacity),
                                                        removal: .move(edge: .leading).combined(with: .opacity)))
                        }
                    }
                    .frame(maxHeight: .infinity)
                }
            }
            .clipShape(shape)

            if dropping { DropOverlay().transition(.opacity.combined(with: .scale(scale: 1.03))) }
            if pc.modelMenu {
                Color.black.opacity(0.001).onTapGesture { withAnimation(UI.snappy) { pc.modelMenu = false } }
                ModelMenu()
                    .padding(.top, 62)
                    .frame(maxHeight: .infinity, alignment: .top)
                    .transition(.scale(scale: 0.92, anchor: .top).combined(with: .opacity))
            }
            if let t = pc.toast {
                Toast(text: t).frame(maxHeight: .infinity, alignment: .bottom).padding(.bottom, 130)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .id(t)
            }
            if pc.flash { shape.fill(Color.white.opacity(0.55)).allowsHitTesting(false) }
        }
        .foregroundStyle(UI.text)
        .environment(\.colorScheme, .dark)
        .onDrop(of: [.fileURL, .image], isTargeted: Binding(get: { dropping }, set: { v in withAnimation(UI.snappy) { dropping = v } })) { providers in
            Drop.load(providers)
            return true
        }
    }
}

enum Drop {
    @MainActor static func load(_ providers: [NSItemProvider]) {
        for p in providers {
            if p.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                _ = p.loadDataRepresentation(forTypeIdentifier: UTType.fileURL.identifier) { data, _ in
                    guard let data, let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                    DispatchQueue.main.async { PanelController.shared.attach(urls: [url]) }
                }
            } else if p.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                _ = p.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { data, _ in
                    guard let data else { return }
                    DispatchQueue.main.async {
                        guard let img = NSImage(data: data), let a = try? Attachments.from(image: img, name: "Dropped image.jpg") else { return }
                        withAnimation(UI.spring) { ChatModel.shared.addAttachments([a]) }
                    }
                }
            }
        }
    }
}

struct DropOverlay: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: UI.radius, style: .continuous).fill(Color.black.opacity(0.35))
            RoundedRectangle(cornerRadius: UI.radius - 8, style: .continuous)
                .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [8, 6])).foregroundStyle(UI.accent).padding(8)
            VStack(spacing: 10) {
                Image(systemName: "tray.and.arrow.down.fill").font(.system(size: 34)).foregroundStyle(UI.accent)
                Text("Drop to attach").font(.system(size: 15, weight: .semibold))
                Text("Images, PDFs, text & code").font(.system(size: 12)).foregroundStyle(UI.dim)
            }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Header

struct Header: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @EnvironmentObject var chat: ChatModel
    @EnvironmentObject var voice: Voice

    var orbState: OrbState {
        voice.listening ? .listening : voice.speaking ? .speaking : chat.isStreaming ? .thinking : .idle
    }

    var title: String {
        if pc.page == .settings { return "Settings" }
        return chat.isEmpty ? "Glass" : chat.current.title
    }

    var body: some View {
        HStack(spacing: 10) {
            Orb(size: 26, state: orbState, level: voice.level)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 14, weight: .semibold)).lineLimit(1)
                    .id(title).transition(.opacity.combined(with: .move(edge: .bottom)))
                Button { withAnimation(UI.snappy) { pc.modelMenu.toggle() } } label: {
                    HStack(spacing: 4) {
                        Circle().fill(s.hasKey(s.provider) ? Color.green : Color.orange).frame(width: 6, height: 6)
                        Text("\(s.providerLabel) · \(s.model)").lineLimit(1)
                        Image(systemName: "chevron.down").font(.system(size: 8, weight: .bold))
                            .rotationEffect(.degrees(pc.modelMenu ? 180 : 0))
                    }
                    .font(.system(size: 11)).foregroundStyle(UI.dim)
                }
                .buttonStyle(.plain)
                .help("Switch model ⌘K")
            }
            .animation(UI.spring, value: title)
            Spacer(minLength: 4)
            IconButton(symbol: "square.and.pencil", help: "New chat ⌘N") {
                withAnimation(UI.spring) { chat.newChat(); pc.page = .chat }
            }
            if !pc.full {
                IconButton(symbol: pc.pinned ? "pin.fill" : "pin", help: "Keep open ⌘P", active: pc.pinned) { pc.pinned.toggle() }
                    .transition(.scale.combined(with: .opacity))
            }
            IconButton(symbol: "gearshape", help: "Settings ⌘,", active: pc.page == .settings) { pc.openSettings() }
            IconButton(symbol: pc.full ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right",
                       help: pc.full ? "Exit fullscreen ⌘F" : "Fullscreen ⌘F") { pc.toggleFull() }
            IconButton(symbol: "xmark", help: "Close  Esc") { pc.hide() }
        }
        .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 11)
    }
}

// MARK: - Chat pane

struct ChatPane: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var chat: ChatModel

    var body: some View {
        VStack(spacing: 0) {
            if chat.isEmpty {
                Welcome().frame(maxHeight: .infinity).transition(.opacity.combined(with: .scale(scale: 0.96)))
            } else {
                Conversation().transition(.opacity)
            }
            Composer()
                .frame(maxWidth: pc.full ? 800 : .infinity)
        }
        .animation(UI.spring, value: chat.isEmpty)
    }
}

struct Welcome: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @EnvironmentObject var chat: ChatModel
    @State private var halo = false

    struct Suggestion: Identifiable { let id = UUID(); let icon: String; let title: String; let sub: String; let run: () -> Void }

    var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 5 ? "Up late?" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
    }

    var suggestions: [Suggestion] {
        let c = chat, p = pc
        return [
            Suggestion(icon: "camera.viewfinder", title: "What's on my screen?", sub: "Screenshot behind the glass") { p.captureScreen() },
            Suggestion(icon: "waveform", title: "Talk it through", sub: "Hands-free voice mode") { p.toggleVoiceMode() },
            Suggestion(icon: "doc.text.magnifyingglass", title: "Summarize a file", sub: "PDF, image, code…") { c.draft = "Summarize this and pull out the key points."; p.pickFiles() },
            Suggestion(icon: "envelope", title: "Draft an email", sub: "Clear, friendly, short") { c.draft = "Help me write a short, friendly email to "; p.focusTick += 1 },
            Suggestion(icon: "lightbulb", title: "Brainstorm", sub: "10 ideas, then the best 3") { c.draft = "Brainstorm 10 ideas for "; p.focusTick += 1 },
            Suggestion(icon: "chevron.left.forwardslash.chevron.right", title: "Fix my code", sub: "Paste it or drop a file") { c.draft = "Find the bug in this code and explain the fix:\n\n"; p.focusTick += 1 },
        ]
    }

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 18) {
                Spacer(minLength: pc.full ? 80 : 30)
                ZStack {
                    Circle().fill(UI.accent).frame(width: 150, height: 150).blur(radius: 40)
                        .opacity(halo ? 0.55 : 0.3).scaleEffect(halo ? 1.12 : 0.92)
                    Orb(size: 78)
                }
                .appear(0, y: 20)
                .onAppear { withAnimation(.easeInOut(duration: 2.6).repeatForever(autoreverses: true)) { halo = true } }

                VStack(spacing: 6) {
                    Text(greeting).font(.system(size: 24, weight: .bold, design: .rounded))
                    Text(s.hasKey(s.provider) ? "Ask anything, attach files, or just talk." : "Add an API key to get started.")
                        .font(.system(size: 13)).foregroundStyle(UI.dim)
                }
                .appear(0.06)

                if !s.hasKey(s.provider) {
                    PillButton(title: "Add API key", symbol: "key.fill", selected: true) { pc.openSettings() }.appear(0.1)
                }

                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: pc.full ? 3 : 2), spacing: 10) {
                    ForEach(Array(suggestions.enumerated()), id: \.element.id) { i, sg in
                        SuggestionCard(icon: sg.icon, title: sg.title, sub: sg.sub, run: sg.run).appear(0.12 + Double(i) * 0.045, y: 14)
                    }
                }
                .frame(maxWidth: pc.full ? 680 : .infinity)
                .padding(.horizontal, 16)

                Text("⌘K models · ⌘⇧S screen · ⌘⇧V voice · ⌘O files")
                    .font(.system(size: 10.5)).foregroundStyle(UI.faint).appear(0.45)
                Spacer(minLength: 12)
            }
            .frame(maxWidth: .infinity)
        }
    }
}

struct SuggestionCard: View {
    var icon: String, title: String, sub: String
    var run: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: run) {
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: icon).font(.system(size: 15, weight: .semibold)).foregroundStyle(UI.accent)
                    .scaleEffect(hover ? 1.15 : 1).rotationEffect(.degrees(hover ? -6 : 0))
                Text(title).font(.system(size: 12.5, weight: .semibold)).lineLimit(1)
                Text(sub).font(.system(size: 11)).foregroundStyle(UI.faint).lineLimit(1)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .chip(14, hover: hover)
            .offset(y: hover ? -2 : 0)
            .shadow(color: .black.opacity(hover ? 0.25 : 0), radius: 10, y: 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
    }
}

struct Conversation: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var chat: ChatModel

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    ForEach(Array(chat.current.messages.enumerated()), id: \.element.id) { i, m in
                        Group {
                            if m.role == "user" { UserMessage(index: i, m: m) } else { AssistantMessage(index: i, m: m) }
                        }
                        .id(m.id)
                        .transition(.asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity), removal: .opacity))
                    }
                    Color.clear.frame(height: 6).id("bottom")
                }
                .padding(.horizontal, 18).padding(.top, 14)
                .frame(maxWidth: pc.full ? 800 : .infinity)
                .frame(maxWidth: .infinity)
                .animation(UI.spring, value: chat.current.messages.count)
            }
            .onAppear { proxy.scrollTo("bottom", anchor: .bottom) }
            .onChange(of: chat.current.id) { _, _ in proxy.scrollTo("bottom", anchor: .bottom) }
            .onChange(of: chat.current.messages.count) { _, _ in withAnimation(UI.spring) { proxy.scrollTo("bottom", anchor: .bottom) } }
            .onChange(of: chat.current.messages.last?.content.count ?? 0) { _, _ in
                if chat.isStreaming { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }
}

struct UserMessage: View {
    var index: Int
    var m: ChatMessage
    @EnvironmentObject var chat: ChatModel
    @State private var hover = false

    var body: some View {
        VStack(alignment: .trailing, spacing: 6) {
            if !m.attachments.isEmpty {
                HStack(spacing: 6) {
                    ForEach(m.attachments) { a in AttachmentChip(a: a, large: m.attachments.count == 1) }
                }
            }
            if !m.content.isEmpty {
                Text(m.content)
                    .font(.system(size: 13.5)).lineSpacing(3)
                    .textSelection(.enabled)
                    .padding(.horizontal, 13).padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(LinearGradient(colors: [Color.white.opacity(0.2), Color.white.opacity(0.11)], startPoint: .top, endPoint: .bottom))
                            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Color.white.opacity(0.2), lineWidth: 0.8)))
            }
            HStack(spacing: 2) {
                MiniAction(symbol: "pencil", help: "Edit & resend") { withAnimation(UI.spring) { chat.beginEdit(index) } }
                MiniAction(symbol: "doc.on.doc", help: "Copy") { copy(m.content) }
            }
            .opacity(hover ? 1 : 0)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.leading, 40)
        .opacity(chat.editingIndex.map { index >= $0 ? 0.45 : 1 } ?? 1)
        .onHover { h in withAnimation(UI.soft) { hover = h } }
    }
}

struct AssistantMessage: View {
    var index: Int
    var m: ChatMessage
    @EnvironmentObject var chat: ChatModel
    @EnvironmentObject var voice: Voice
    @State private var hover = false
    @State private var copied = false

    var streaming: Bool { chat.streamingID == m.id }
    var isLast: Bool { index == chat.current.messages.count - 1 }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Orb(size: 20, state: streaming ? .thinking : .idle).padding(.top, 1)
            VStack(alignment: .leading, spacing: 8) {
                if streaming && m.content.isEmpty {
                    HStack(spacing: 10) { ThinkingDots(); Shimmer(text: m.attachments.isEmpty ? "Thinking" : "Looking") }
                        .frame(height: 20)
                        .transition(.opacity)
                } else if m.error {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(m.content, systemImage: "exclamationmark.triangle.fill")
                            .font(.system(size: 13)).foregroundStyle(Color(hex: "#FFB4A8")!)
                        PillButton(title: "Try again", symbol: "arrow.clockwise") { chat.regenerate() }
                    }
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 14).fill(Color.red.opacity(0.14)))
                } else {
                    MarkdownView(text: m.content, streaming: streaming)
                }
                if !streaming && !m.content.isEmpty && !m.error {
                    HStack(spacing: 2) {
                        MiniAction(symbol: copied ? "checkmark" : "doc.on.doc", help: "Copy") {
                            copy(m.content)
                            withAnimation(UI.snappy) { copied = true }
                            DispatchQueue.main.asyncAfter(deadline: .now() + 1.3) { withAnimation { copied = false } }
                        }
                        MiniAction(symbol: voice.speaking ? "stop.fill" : "speaker.wave.2", help: "Read aloud") {
                            voice.speaking ? voice.stopSpeaking() : voice.speak(m.content)
                        }
                        if isLast { MiniAction(symbol: "arrow.clockwise", help: "Regenerate") { chat.regenerate() } }
                        Text("\(m.model) · \(ChatModel.relative(m.time))")
                            .font(.system(size: 10.5)).foregroundStyle(UI.faint).lineLimit(1).padding(.leading, 4)
                    }
                    .opacity(hover || isLast ? 1 : 0)
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .animation(UI.soft, value: streaming)
        }
        .onHover { h in withAnimation(UI.soft) { hover = h } }
    }
}

struct MiniAction: View {
    var symbol: String
    var help: String
    var action: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 11, weight: .medium))
                .foregroundStyle(hover ? .white : UI.faint)
                .frame(width: 24, height: 22)
                .background(RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(hover ? 0.12 : 0)))
                .contentTransition(.symbolEffectIfAvailable)
        }
        .buttonStyle(.plain).help(help)
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
    }
}

func copy(_ s: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(s, forType: .string)
}

// MARK: - Composer

struct Composer: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @EnvironmentObject var chat: ChatModel
    @EnvironmentObject var voice: Voice
    @FocusState private var focused: Bool

    var canSend: Bool { !chat.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !chat.pending.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if chat.editingIndex != nil {
                HStack(spacing: 6) {
                    Image(systemName: "pencil").font(.system(size: 11, weight: .bold)).foregroundStyle(UI.accent)
                    Text("Editing — sending replaces the replies after it").font(.system(size: 11.5)).foregroundStyle(UI.dim)
                    Spacer()
                    Button("Cancel") { withAnimation(UI.spring) { chat.cancelEdit() } }
                        .buttonStyle(.plain).font(.system(size: 11.5, weight: .semibold))
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
            if !chat.pending.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(chat.pending) { a in
                            AttachmentChip(a: a) { withAnimation(UI.spring) { chat.pending.removeAll { $0.id == a.id } } }
                                .transition(.scale(scale: 0.6).combined(with: .opacity))
                        }
                    }
                    .padding(.top, 7).padding(.horizontal, 2)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            ZStack(alignment: .topLeading) {
                if voice.listening {
                    HStack(spacing: 12) {
                        VoiceBars(level: voice.level, color: Color(hex: "#FF8A8A")!)
                        Text(voice.partial.isEmpty ? (voice.mode ? "Listening… just talk" : "Listening…") : voice.partial)
                            .font(.system(size: 13.5)).foregroundStyle(voice.partial.isEmpty ? UI.dim : .white)
                            .lineLimit(3)
                            .animation(UI.soft, value: voice.partial)
                    }
                    .frame(minHeight: 28)
                    .transition(.opacity.combined(with: .scale(scale: 0.97)))
                } else {
                    TextField("", text: $chat.draft, prompt: Text(prompt).foregroundColor(UI.faint), axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .lineLimit(1...9)
                        .focused($focused)
                        .onSubmit { send() }
                        .frame(minHeight: 28, alignment: .center)
                        .transition(.opacity)
                }
            }
            .animation(UI.spring, value: voice.listening)

            HStack(spacing: 4) {
                IconButton(symbol: "paperclip", help: "Attach files ⌘O", size: 28) { pc.pickFiles() }
                IconButton(symbol: "camera.viewfinder", help: "Ask about my screen ⌘⇧S", size: 28) { pc.captureScreen() }
                ModelChip()
                Spacer()
                IconButton(symbol: voice.mode ? "waveform.circle.fill" : "waveform", help: "Voice mode ⌘⇧V", size: 28,
                           active: voice.mode, tint: voice.mode ? Color(hex: "#FF8A8A")! : .white) { pc.toggleVoiceMode() }
                ZStack {
                    if voice.listening && !voice.mode {
                        Circle().fill(Color.red.opacity(0.35))
                            .frame(width: 28, height: 28).scaleEffect(1.2 + CGFloat(voice.level) * 0.7)
                    }
                    IconButton(symbol: voice.listening && !voice.mode ? "mic.fill" : "mic", help: "Dictate", size: 28,
                               active: voice.listening && !voice.mode, tint: .white) { pc.dictate() }
                }
                SendButton(enabled: canSend, streaming: chat.isStreaming) {
                    chat.isStreaming ? chat.stop() : send()
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(Color.black.opacity(0.2))
                .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .strokeBorder(focused ? Color.white.opacity(0.32) : UI.hair, lineWidth: focused ? 1.2 : 0.8)))
        .shadow(color: .black.opacity(focused ? 0.25 : 0.12), radius: focused ? 16 : 8, y: 4)
        .scaleEffect(focused ? 1 : 0.995)
        .animation(UI.spring, value: focused)
        .animation(UI.spring, value: chat.pending.count)
        .animation(UI.spring, value: chat.editingIndex)
        .padding(.horizontal, 12).padding(.bottom, 12).padding(.top, 6)
        .onAppear { focused = true }
        .onChange(of: pc.focusTick) { _, _ in focused = true }
    }

    var prompt: String {
        if !s.hasKey(s.provider) { return "Add an API key in Settings…" }
        if chat.pending.contains(where: { $0.kind == "image" }) { return "Ask about the image…" }
        return chat.isEmpty ? "Ask anything…" : "Reply…"
    }

    func send() {
        guard canSend, !chat.isStreaming else { return }
        withAnimation(UI.spring) { chat.send() }
    }
}

struct SendButton: View {
    var enabled: Bool
    var streaming: Bool
    var action: () -> Void
    @State private var hover = false
    @State private var pop = false
    var body: some View {
        Button {
            withAnimation(.spring(response: 0.22, dampingFraction: 0.45)) { pop = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) { withAnimation(UI.spring) { pop = false } }
            action()
        } label: {
            ZStack {
                Circle().fill(enabled || streaming ? AnyShapeStyle(UI.accent) : AnyShapeStyle(Color.white.opacity(0.12)))
                Image(systemName: streaming ? "stop.fill" : "arrow.up")
                    .font(.system(size: streaming ? 11 : 13, weight: .bold))
                    .foregroundStyle(enabled || streaming ? Color.black.opacity(0.8) : UI.faint)
                    .contentTransition(.symbolEffectIfAvailable)
            }
            .frame(width: 30, height: 30)
            .scaleEffect(pop ? 0.8 : hover && enabled ? 1.08 : 1)
            .shadow(color: Color(hex: "#A98BFF")!.opacity(enabled ? 0.55 : 0), radius: 10)
        }
        .buttonStyle(.plain)
        .disabled(!enabled && !streaming)
        .help(streaming ? "Stop  Esc" : "Send  ⏎")
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
        .animation(UI.spring, value: enabled)
        .animation(UI.spring, value: streaming)
    }
}

struct ModelChip: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @State private var hover = false
    var body: some View {
        Button { withAnimation(UI.snappy) { pc.modelMenu.toggle() } } label: {
            HStack(spacing: 5) {
                Image(systemName: "sparkles").font(.system(size: 10, weight: .semibold))
                Text(shortName(s.model)).lineLimit(1)
            }
            .font(.system(size: 11.5, weight: .medium)).foregroundStyle(hover ? .white : UI.dim)
            .padding(.horizontal, 9).frame(height: 26)
            .chip(13, hover: hover)
            .frame(maxWidth: 150)
        }
        .buttonStyle(.plain)
        .help("Switch model ⌘K")
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
    }
}

func shortName(_ m: String) -> String {
    let id = m.split(separator: "/").last.map(String.init) ?? m
    return id.replacingOccurrences(of: "claude-", with: "").replacingOccurrences(of: "-latest", with: "")
}

// MARK: - Model menu

struct ModelMenu: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var s: Settings
    @State private var filter = ""
    @State private var lists: [String: [String]] = [:]
    @State private var loading: Set<String> = []
    @FocusState private var focused: Bool

    struct Entry: Identifiable, Hashable { var provider: String; var model: String; var id: String { provider + "|" + model } }

    var sections: [(String, [Entry])] {
        let q = filter.lowercased()
        func ok(_ e: Entry) -> Bool { q.isEmpty || e.model.lowercased().contains(q) || Settings.label(e.provider).lowercased().contains(q) }
        var out: [(String, [Entry])] = []
        let recent = s.recentModels.compactMap { tag -> Entry? in
            let p = tag.split(separator: "|", maxSplits: 1).map(String.init)
            return p.count == 2 && s.hasKey(p[0]) ? Entry(provider: p[0], model: p[1]) : nil
        }.filter(ok)
        if !recent.isEmpty && q.isEmpty { out.append(("Recent", Array(recent.prefix(4)))) }
        for p in s.keyedProviders {
            let models: [String]
            switch p {
            case "anthropic": models = AI.claudeModels
            case "openai": models = Array(Set([s.provider == "openai" ? s.model : "gpt-4.1", "gpt-4.1", "gpt-4.1-mini", "o4-mini"])).sorted()
            default: models = lists[p] ?? (p == "gemini" ? [AI.geminiDefault] : [])
            }
            let e = models.map { Entry(provider: p, model: $0) }.filter(ok)
            if !e.isEmpty || loading.contains(p) { out.append((Settings.label(p), e)) }
        }
        return out
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").font(.system(size: 12)).foregroundStyle(UI.faint)
                TextField("", text: $filter, prompt: Text("Search models").foregroundColor(UI.faint))
                    .textFieldStyle(.plain).font(.system(size: 13)).focused($focused)
            }
            .padding(12)
            Rectangle().fill(UI.hair).frame(height: 1)
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    if s.keyedProviders.isEmpty {
                        Text("Add an API key in Settings to see models.").font(.system(size: 12)).foregroundStyle(UI.dim).padding(12)
                    }
                    ForEach(sections, id: \.0) { title, entries in
                        HStack {
                            Text(title.uppercased()).font(.system(size: 10, weight: .semibold)).foregroundStyle(UI.faint)
                            if loading.contains(entries.first?.provider ?? title.lowercased()) || (entries.isEmpty) { ProgressView().controlSize(.mini) }
                        }
                        .padding(.horizontal, 10).padding(.top, 10).padding(.bottom, 2)
                        ForEach(entries) { e in
                            HoverRow(selected: e.provider == s.provider && e.model == s.model, action: { pick(e) }) { _ in
                                HStack {
                                    Text(e.model).font(.system(size: 12.5)).lineLimit(1)
                                    Spacer()
                                    if title == "Recent" { Text(Settings.label(e.provider)).font(.system(size: 10.5)).foregroundStyle(UI.faint) }
                                    if e.provider == s.provider && e.model == s.model {
                                        Image(systemName: "checkmark").font(.system(size: 10, weight: .bold)).foregroundStyle(UI.accent)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(6)
            }
            .frame(maxHeight: 360)
        }
        .frame(width: 320)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.black.opacity(0.55))
                .background(VisualEffect(material: .hudWindow).clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Color.white.opacity(0.18)))
        .shadow(color: .black.opacity(0.4), radius: 24, y: 10)
        .onAppear { focused = true; load() }
    }

    func load() {
        for p in ["gemini", "groq"] where s.hasKey(p) && lists[p] == nil {
            loading.insert(p)
            let key = s.key(for: p)
            Task {
                let r = (try? await AI.models(provider: p, key: key))?.map { $0.id } ?? []
                withAnimation(UI.soft) { lists[p] = r; loading.remove(p) }
            }
        }
    }

    func pick(_ e: Entry) {
        s.provider = e.provider
        s.model = e.model
        s.rememberModel(e.model)
        withAnimation(UI.snappy) { pc.modelMenu = false }
        pc.show(toast: "Now using \(shortName(e.model))")
    }
}

// MARK: - Chats sidebar (fullscreen)

struct ChatsSidebar: View {
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var chat: ChatModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Chats").font(.system(size: 15, weight: .bold))
                Spacer()
                Text("\(chat.sessions.count)").font(.system(size: 11, weight: .medium)).foregroundStyle(UI.faint)
            }
            .padding(.top, 18).padding(.horizontal, 6)

            Button { withAnimation(UI.spring) { chat.newChat(); pc.page = .chat } } label: {
                HStack(spacing: 8) {
                    Image(systemName: "plus").font(.system(size: 12, weight: .bold))
                    Text("New chat").font(.system(size: 13, weight: .semibold))
                    Spacer()
                    Text("⌘N").font(.system(size: 11)).foregroundStyle(UI.faint)
                }
                .padding(.horizontal, 12).frame(height: 36)
                .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(UI.accent.opacity(0.35)))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Color.white.opacity(0.25)))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass").font(.system(size: 11)).foregroundStyle(UI.faint)
                TextField("", text: $chat.search, prompt: Text("Search chats").foregroundColor(UI.faint))
                    .textFieldStyle(.plain).font(.system(size: 12.5))
            }
            .padding(.horizontal, 10).frame(height: 30).chip(10)

            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 2) {
                    if chat.sessions.isEmpty {
                        Text("Your chats will show up here.").font(.system(size: 12)).foregroundStyle(UI.faint).padding(.top, 20).padding(.horizontal, 6)
                    }
                    ForEach(chat.buckets, id: \.0) { title, items in
                        Text(title).font(.system(size: 10.5, weight: .semibold)).foregroundStyle(UI.faint)
                            .padding(.horizontal, 8).padding(.top, 12).padding(.bottom, 3)
                        ForEach(Array(items.enumerated()), id: \.element.id) { i, c in
                            ChatRow(c: c).appear(Double(min(i, 10)) * 0.025, y: 6)
                        }
                    }
                }
                .animation(UI.spring, value: chat.sessions.map(\.id))
            }
        }
        .padding(.horizontal, 12).padding(.bottom, 12)
        .background(Color.black.opacity(0.08))
    }
}

struct ChatRow: View {
    var c: ChatSession
    @EnvironmentObject var pc: PanelController
    @EnvironmentObject var chat: ChatModel

    var body: some View {
        HoverRow(selected: c.id == chat.current.id, action: { withAnimation(UI.spring) { chat.open(c.id); pc.page = .chat } }) { hover in
            HStack(spacing: 8) {
                if c.pinned { Image(systemName: "pin.fill").font(.system(size: 9)).foregroundStyle(UI.accent) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.title).font(.system(size: 12.5, weight: c.id == chat.current.id ? .semibold : .regular)).lineLimit(1)
                    Text("\(Settings.label(c.provider)) · \(ChatModel.relative(c.updated))").font(.system(size: 10.5)).foregroundStyle(UI.faint).lineLimit(1)
                }
                Spacer(minLength: 0)
                if hover {
                    HStack(spacing: 0) {
                        MiniAction(symbol: c.pinned ? "pin.slash" : "pin", help: c.pinned ? "Unpin" : "Pin") { withAnimation(UI.spring) { chat.togglePin(c.id) } }
                        MiniAction(symbol: "trash", help: "Delete") { withAnimation(UI.spring) { chat.delete(c.id) } }
                    }
                    .transition(.opacity.combined(with: .move(edge: .trailing)))
                }
            }
        }
        .contextMenu {
            Button(c.pinned ? "Unpin" : "Pin") { chat.togglePin(c.id) }
            Button("Copy as Markdown") { chat.exportMarkdown(c.id) }
            Divider()
            Button("Delete", role: .destructive) { chat.delete(c.id) }
        }
    }
}
