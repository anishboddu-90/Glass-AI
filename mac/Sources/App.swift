import AppKit
import SwiftUI

@main
enum GlassMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)   // menu-bar app, no Dock icon
        app.run()
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var status: NSStatusItem!

    func applicationDidFinishLaunching(_ n: Notification) {
        let pc = PanelController.shared
        pc.setUp()
        pc.wireVoice()

        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let b = status.button {
            b.image = NSImage(systemSymbolName: "sparkles", accessibilityDescription: "Glass")
            b.toolTip = "Glass — flick your cursor into a screen edge, or press ⌃⌥Space"
        }
        let menu = NSMenu()
        menu.addItem(item("Open Glass", "g") { pc.toggle() })
        menu.addItem(item("New Chat", "n") { ChatModel.shared.newChat(); if !pc.visible { pc.toggle() } })
        menu.addItem(item("Settings…", ",") { pc.openSettings() })
        menu.addItem(.separator())
        menu.addItem(item("Quit Glass", "q") { NSApp.terminate(nil) })
        status.menu = menu

        // first launch: show the panel so the key can be added
        if Settings.shared.keyedProviders.isEmpty {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { pc.toggle() }
        }
    }

    private var actions: [ActionItem] = []
    private func item(_ title: String, _ key: String, _ run: @escaping () -> Void) -> NSMenuItem {
        let a = ActionItem(run)
        actions.append(a)
        let i = NSMenuItem(title: title, action: #selector(ActionItem.fire), keyEquivalent: key)
        i.target = a
        return i
    }
}

final class ActionItem: NSObject {
    let run: () -> Void
    init(_ r: @escaping () -> Void) { run = r }
    @objc func fire() { run() }
}
