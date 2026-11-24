import AppKit
import Carbon
import SwiftUI

final class GlassWindow: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

/// Window management: edge flicks, sliding in/out, fullscreen, shortcuts, click-through.
/// The window covers the whole visible screen and is transparent; only the panel catches clicks,
/// so going sidebar ⇄ fullscreen is one continuous SwiftUI spring.
@MainActor
final class PanelController: NSObject, ObservableObject, NSWindowDelegate {
    static let shared = PanelController()

    @Published var visible = false
    @Published var full = false
    @Published var side: CGFloat = 1             // -1 left, 1 right
    @Published var pinned = false
    @Published var page: Page = .chat
    @Published var modelMenu = false
    @Published var toast: String?
    @Published var flash = false                 // screenshot flash
    @Published var focusTick = 0                 // bump to focus the composer

    enum Page { case chat, settings }

    static let width: CGFloat = 440
    static let margin: CGFloat = 12

    private var window: GlassWindow!
    private var poll: Timer?
    private var samples: [(t: TimeInterval, x: CGFloat)] = []
    private var wasEdge = false
    private var lastFire: TimeInterval = 0
    private var hideWork: DispatchWorkItem?
    private var toastWork: DispatchWorkItem?
    var holdOpen = false                          // while file pickers / permission prompts are up

    func setUp() {
        window = GlassWindow(contentRect: NSScreen.main?.visibleFrame ?? .zero,
                             styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        window.isMovable = false
        window.hidesOnDeactivate = false
        window.becomesKeyOnlyIfNeeded = false
        window.delegate = self
        window.sharingType = .readOnly
        let host = NSHostingView(rootView: RootView()
            .environmentObject(self)
            .environmentObject(Settings.shared)
            .environmentObject(ChatModel.shared)
            .environmentObject(Voice.shared))
        host.layer?.backgroundColor = .clear
        window.contentView = host

        ChatModel.shared.onToast = { [weak self] in self?.show(toast: $0) }
        Voice.shared.onError = { [weak self] in self?.show(toast: $0) }

        poll = Timer.scheduledTimer(withTimeInterval: 1.0 / 120, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        RunLoop.main.add(poll!, forMode: .common)
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in self?.key(e) ?? e }
        HotKey.register { [weak self] in self?.toggle() }
    }

    // MARK: geometry

    private var screen: NSScreen { window.screen ?? NSScreen.main ?? NSScreen.screens[0] }

    /// Panel rect in window coordinates (bottom-left origin), matching RootView's layout.
    private func panelRect(in size: CGSize) -> CGRect {
        let m = PanelController.margin
        if full { return CGRect(x: m, y: m, width: size.width - m * 2, height: size.height - m * 2) }
        let w = PanelController.width
        return CGRect(x: side < 0 ? m : size.width - w - m, y: m, width: w, height: size.height - m * 2)
    }

    // MARK: show / hide

    func show(side s: CGFloat, on scr: NSScreen) {
        hideWork?.cancel()
        if window.screen != scr || !window.isVisible { window.setFrame(scr.visibleFrame, display: false) }
        if !visible { side = s }
        window.ignoresMouseEvents = false
        window.orderFrontRegardless()
        window.makeKey()
        withAnimation(UI.spring) { visible = true }
        focusTick += 1
    }

    func hide() {
        guard visible else { return }
        Voice.shared.cancel()
        withAnimation(.spring(response: 0.36, dampingFraction: 0.9)) { visible = false; modelMenu = false }
        let w = DispatchWorkItem { [weak self] in
            guard let self, !self.visible else { return }
            self.window.orderOut(nil)
            if self.full { self.full = false }
        }
        hideWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: w)
    }

    func toggle() {
        if visible { hide() } else { show(side: side, on: screenUnderMouse()) }
    }

    func toggleFull() {
        withAnimation(.spring(response: 0.5, dampingFraction: 0.82)) { full.toggle() }
    }

    func openSettings() {
        if !visible { show(side: side, on: screenUnderMouse()) }
        withAnimation(UI.spring) { page = page == .settings ? .chat : .settings; modelMenu = false }
    }

    func show(toast t: String) {
        toastWork?.cancel()
        withAnimation(UI.snappy) { toast = t }
        let w = DispatchWorkItem { [weak self] in withAnimation(UI.soft) { self?.toast = nil } }
        toastWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4, execute: w)
    }

    private func screenUnderMouse() -> NSScreen {
        let p = NSEvent.mouseLocation
        return NSScreen.screens.first { NSMouseInRect(p, $0.frame, false) } ?? NSScreen.main ?? NSScreen.screens[0]
    }

    func windowDidResignKey(_ n: Notification) {
        // click away to dismiss (unless pinned, fullscreen, or a picker is open)
        guard visible, !pinned, !full, !holdOpen else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            guard let self, !self.window.isKeyWindow, !self.holdOpen, !Voice.shared.listening else { return }
            self.hide()
        }
    }

    // MARK: flick detection + click-through (120 Hz)

    private func tick() {
        let p = NSEvent.mouseLocation
        let now = ProcessInfo.processInfo.systemUptime

        // only the panel itself should take clicks
        if window.isVisible {
            let f = window.frame
            let local = CGPoint(x: p.x - f.minX, y: p.y - f.minY)
            let inside = visible && panelRect(in: f.size).contains(local)
            if window.ignoresMouseEvents == inside { window.ignoresMouseEvents = !inside }
        }

        samples.append((now, p.x))
        samples.removeAll { now - $0.t > 0.15 }
        guard let scr = NSScreen.screens.first(where: { NSMouseInRect(p, $0.frame, false) }) else { return }
        let g = scr.frame
        let s: CGFloat = p.x <= g.minX + 1 ? -1 : (p.x >= g.maxX - 2 ? 1 : 0)
        let atEdge = s != 0
        if atEdge, !wasEdge, now - lastFire > 0.7, NSEvent.pressedMouseButtons == 0,
           let old = samples.first(where: { now - $0.t <= 0.09 }) {
            let dt = max(0.001, now - old.t)
            let travel = (p.x - old.x) * s
            let k = max(0, min(2, Settings.shared.sensitivity))
            let speeds: [CGFloat] = [2.4, 1.6, 1.05], dists: [CGFloat] = [0.16, 0.10, 0.06]
            if travel / dt > g.width * speeds[k], travel > g.width * dists[k] {
                lastFire = now
                if visible && side == s && !full { hide() }
                else {
                    if visible && side != s && !full { withAnimation(UI.spring) { side = s } }
                    show(side: s, on: scr)
                }
            }
        }
        wasEdge = atEdge
    }

    // MARK: keyboard

    private func key(_ e: NSEvent) -> NSEvent? {
        guard e.window === window else { return e }
        let cmd = e.modifierFlags.contains(.command), shift = e.modifierFlags.contains(.shift)
        let chars = e.charactersIgnoringModifiers?.lowercased() ?? ""
        let chat = ChatModel.shared
        switch (e.keyCode, cmd, shift, chars) {
        case (53, _, _, _):                                   // Esc: close the innermost thing
            if modelMenu { withAnimation(UI.snappy) { modelMenu = false } }
            else if chat.isStreaming { chat.stop() }
            else if Voice.shared.listening || Voice.shared.speaking { Voice.shared.cancel() }
            else if chat.editingIndex != nil { chat.cancelEdit() }
            else if page == .settings { withAnimation(UI.spring) { page = .chat } }
            else if full { toggleFull() }
            else { hide() }
            return nil
        case (_, true, false, "n"): withAnimation(UI.spring) { chat.newChat(); page = .chat }; return nil
        case (_, true, false, "k"): withAnimation(UI.snappy) { modelMenu.toggle() }; return nil
        case (_, true, false, ","): openSettings(); return nil
        case (_, true, false, "f"): toggleFull(); return nil
        case (_, true, false, "p"): pinned.toggle(); show(toast: pinned ? "Pinned open" : "Unpinned"); return nil
        case (_, true, true, "s"): captureScreen(); return nil
        case (_, true, true, "v"): toggleVoiceMode(); return nil
        case (_, true, false, "o"): pickFiles(); return nil
        case (_, true, false, "v"):
            // paste images / files as attachments; plain text falls through to the text field
            let pb = NSPasteboard.general
            if pb.string(forType: .string) == nil {
                let a = Attachments.fromPasteboard()
                if !a.isEmpty { withAnimation(UI.spring) { chat.addAttachments(a) }; return nil }
            }
            return e
        case (126, false, false, _) where chat.draft.isEmpty && chat.editingIndex == nil && !chat.isStreaming:
            chat.editLast(); return nil                        // ↑ edits your last message
        default: return e
        }
    }

    // MARK: actions shared by the UI

    func pickFiles() {
        holdOpen = true
        let p = NSOpenPanel()
        p.allowsMultipleSelection = true
        p.canChooseDirectories = false
        p.level = .modalPanel
        NSApp.activate(ignoringOtherApps: true)
        p.begin { [weak self] r in
            MainActor.assumeIsolated {
                self?.holdOpen = false
                self?.window.makeKey()
                guard r == .OK else { return }
                self?.attach(urls: p.urls)
            }
        }
    }

    func attach(urls: [URL]) {
        var list: [Attachment] = []
        for u in urls {
            do { list.append(try Attachments.from(url: u)) } catch { show(toast: error.localizedDescription) }
        }
        withAnimation(UI.spring) { ChatModel.shared.addAttachments(list) }
    }

    /// Screenshot of whatever is behind the panel, attached to the next message.
    func captureScreen() {
        holdOpen = true
        let scr = screen
        Task {
            defer { holdOpen = false }
            do {
                let a = try await Attachments.captureScreen(of: scr)
                withAnimation(.easeOut(duration: 0.08)) { flash = true }
                withAnimation(.easeOut(duration: 0.5).delay(0.1)) { flash = false }
                withAnimation(UI.spring) { ChatModel.shared.addAttachments([a]) }
                if ChatModel.shared.draft.isEmpty { ChatModel.shared.draft = "What's on my screen?" }
                focusTick += 1
            } catch {
                show(toast: "Allow Screen Recording for Glass in System Settings → Privacy & Security")
            }
        }
    }

    /// Hands-free: listen → send → (speak) → listen…
    func toggleVoiceMode() {
        let v = Voice.shared
        if v.mode || v.listening { v.cancel(); return }
        v.mode = true
        v.start()
    }

    func dictate() {
        let v = Voice.shared
        if v.listening { v.finish(); return }
        v.mode = false
        v.start()
    }

    func wireVoice() {
        let v = Voice.shared, chat = ChatModel.shared
        v.onFinal = { text in
            if v.mode { chat.send(text) }
            else { chat.draft = chat.draft.isEmpty ? text : chat.draft + " " + text; PanelController.shared.focusTick += 1 }
        }
        chat.onReplyFinished = { text in
            // speaking finishes → voice mode starts listening again
            if v.mode || Settings.shared.speakReplies { v.speak(text) }
        }
    }
}

// MARK: - Global hotkey ⌃⌥Space

enum HotKey {
    nonisolated(unsafe) static var action: (() -> Void)?
    nonisolated(unsafe) static var ref: EventHotKeyRef?

    static func register(_ a: @escaping () -> Void) {
        action = a
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async { HotKey.action?() }
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: OSType(0x474C5353), id: 1)
        RegisterEventHotKey(UInt32(kVK_Space), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &ref)
    }
}
