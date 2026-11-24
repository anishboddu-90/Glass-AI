import AppKit
import Foundation
import ScreenCaptureKit
import UniformTypeIdentifiers

struct Attachment: Codable, Identifiable, Equatable, Hashable {
    var id = UUID()
    var name: String
    var kind: String          // image | pdf | text
    var mediaType: String
    var data: String = ""     // base64 (image / pdf)
    var text: String = ""     // contents (text)
    var bytes: Int = 0

    var thumbnail: NSImage? {
        guard kind == "image", let d = Data(base64Encoded: data) else { return nil }
        return NSImage(data: d)
    }
}

enum Attachments {
    static let maxSide: CGFloat = 1600
    static let textExt: Set<String> = ["txt", "md", "markdown", "csv", "tsv", "json", "xml", "yaml", "yml", "toml", "ini", "log", "env",
                                       "html", "htm", "css", "scss", "js", "jsx", "ts", "tsx", "py", "rb", "go", "rs", "java", "kt",
                                       "c", "h", "cpp", "hpp", "cs", "swift", "m", "php", "sh", "sql", "lua", "r", "dart", "vue", "svelte", "tex", "conf", "cfg"]

    static func from(url: URL) throws -> Attachment {
        let ext = url.pathExtension.lowercased()
        let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        if let type = UTType(filenameExtension: ext), type.conforms(to: .image), let img = NSImage(contentsOf: url) {
            return try from(image: img, name: url.lastPathComponent)
        }
        if ext == "pdf" {
            guard size <= 30 * 1024 * 1024 else { throw AIError.message("\(url.lastPathComponent) is larger than 30 MB.") }
            let d = try Data(contentsOf: url)
            return Attachment(name: url.lastPathComponent, kind: "pdf", mediaType: "application/pdf", data: d.base64EncodedString(), bytes: d.count)
        }
        let d = try Data(contentsOf: url)
        let looksText = textExt.contains(ext) || !d.prefix(4096).contains(0)
        guard looksText else { throw AIError.message("Can't attach \(url.lastPathComponent) — use images, PDFs, or text/code files.") }
        guard d.count <= 400 * 1024 else { throw AIError.message("\(url.lastPathComponent) is too large to send as text (max 400 KB).") }
        return Attachment(name: url.lastPathComponent, kind: "text", mediaType: "text/plain",
                          text: String(decoding: d, as: UTF8.self), bytes: d.count)
    }

    /// Re-encodes as JPEG, shrinking anything huge so requests stay fast.
    static func from(image: NSImage, name: String) throws -> Attachment {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw AIError.message("Couldn't read that image.") }
        return try from(cgImage: cg, name: name)
    }

    static func from(cgImage cg: CGImage, name: String) throws -> Attachment {
        let w = CGFloat(cg.width), h = CGFloat(cg.height)
        let k = min(1, maxSide / max(w, h))
        let tw = Int(w * k), th = Int(h * k)
        guard let ctx = CGContext(data: nil, width: tw, height: th, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
            throw AIError.message("Couldn't process that image.")
        }
        ctx.interpolationQuality = .high
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: tw, height: th))
        guard let scaled = ctx.makeImage() else { throw AIError.message("Couldn't process that image.") }
        let rep = NSBitmapImageRep(cgImage: scaled)
        guard let jpg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.88]) else { throw AIError.message("Couldn't encode that image.") }
        return Attachment(name: name, kind: "image", mediaType: "image/jpeg", data: jpg.base64EncodedString(), bytes: jpg.count)
    }

    static func fromPasteboard() -> [Attachment] {
        let pb = NSPasteboard.general
        if let urls = pb.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], !urls.isEmpty {
            return urls.compactMap { try? from(url: $0) }
        }
        if let img = NSImage(pasteboard: pb), let a = try? from(image: img, name: "Pasted image.jpg") { return [a] }
        return []
    }

    /// Screenshot of the display under the panel, with Glass's own windows left out —
    /// so you're asking about exactly what's behind the sidebar. Needs Screen Recording permission once.
    static func captureScreen(of screen: NSScreen) async throws -> Attachment {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        let num = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value
        guard let display = content.displays.first(where: { $0.displayID == num }) ?? content.displays.first else {
            throw AIError.message("No display found.")
        }
        let mine = content.applications.filter { $0.bundleIdentifier == Bundle.main.bundleIdentifier }
        let filter = SCContentFilter(display: display, excludingApplications: mine, exceptingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.width = Int(CGFloat(display.width) * screen.backingScaleFactor)
        cfg.height = Int(CGFloat(display.height) * screen.backingScaleFactor)
        cfg.showsCursor = false
        let cg = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: cfg)
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        return try from(cgImage: cg, name: "Screen \(f.string(from: Date())).jpg")
    }

    static func sizeText(_ n: Int) -> String {
        if n < 1024 { return "\(n) B" }
        if n < 1024 * 1024 { return "\(n / 1024) KB" }
        return String(format: "%.1f MB", Double(n) / 1048576)
    }
}
