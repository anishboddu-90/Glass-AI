import AppKit
import SwiftUI

// MARK: - Palette & motion

enum UI {
    static let radius: CGFloat = 26
    static let text = Color.white
    static let dim = Color.white.opacity(0.62)
    static let faint = Color.white.opacity(0.38)
    static let hair = Color.white.opacity(0.14)
    static let fill = Color.white.opacity(0.08)
    static let fillHover = Color.white.opacity(0.15)
    static let accent = LinearGradient(colors: [Color(hex: "#8FE3FF")!, Color(hex: "#A98BFF")!, Color(hex: "#FF9ED8")!],
                                       startPoint: .topLeading, endPoint: .bottomTrailing)
    static let spring = Animation.spring(response: 0.42, dampingFraction: 0.8)
    static let snappy = Animation.spring(response: 0.28, dampingFraction: 0.72)
    static let soft = Animation.easeOut(duration: 0.22)
}

// MARK: - Liquid glass

/// Real Liquid Glass (live refraction by the system) on macOS 26; layered vibrancy before that.
struct GlassSurface<S: InsettableShape>: View {
    var shape: S
    var tint: Color
    var strength: Double
    var style: String
    var glow: Color? = nil

    var body: some View {
        ZStack {
            base
            // edge glow: violet while thinking, red while listening
            if let glow {
                shape.strokeBorder(glow.opacity(0.85), lineWidth: 1.6)
                    .blur(radius: 6)
                    .transition(.opacity)
            }
        }
        .animation(UI.soft, value: glow == nil)
    }

    @ViewBuilder private var base: some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            ZStack {
                if style == "frosted" { VisualEffect(material: .hudWindow).clipShape(shape) }
                Color.clear
                    .glassEffect(style == "clear" ? .clear.tint(tint.opacity(strength)) : .regular.tint(tint.opacity(strength)),
                                 in: shape)
            }
        } else {
            fallback
        }
        #else
        fallback
        #endif
    }

    private var fallback: some View {
        ZStack {
            VisualEffect(material: style == "clear" ? .underWindowBackground : .hudWindow)
            tint.opacity(strength)
            // glossy top sheen + rim light so it reads as glass, not frosted plastic
            LinearGradient(colors: [.white.opacity(0.16), .clear, .clear, .white.opacity(0.05)],
                           startPoint: .top, endPoint: .bottom)
        }
        .clipShape(shape)
        .overlay(shape.strokeBorder(
            LinearGradient(colors: [.white.opacity(0.55), .white.opacity(0.08), .white.opacity(0.22)],
                           startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1))
    }
}

struct VisualEffect: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.material = material
        v.blendingMode = .behindWindow
        v.state = .active
        return v
    }
    func updateNSView(_ v: NSVisualEffectView, context: Context) { v.material = material }
}

/// Small glass chip used for buttons, bubbles and menus.
struct Chip: ViewModifier {
    var radius: CGFloat = 12
    var hover = false
    var selected = false
    func body(content: Content) -> some View {
        content.background(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(Color.white.opacity(selected ? 0.22 : hover ? 0.15 : 0.08))
                .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(Color.white.opacity(selected ? 0.35 : 0.12), lineWidth: 0.8)))
    }
}

extension View {
    func chip(_ radius: CGFloat = 12, hover: Bool = false, selected: Bool = false) -> some View {
        modifier(Chip(radius: radius, hover: hover, selected: selected))
    }

    /// Fade + rise in with an optional delay — used for staggered entrances everywhere.
    func appear(_ delay: Double = 0, y: CGFloat = 10) -> some View { modifier(Appear(delay: delay, y: y)) }
}

struct Appear: ViewModifier {
    var delay: Double
    var y: CGFloat
    @State private var on = false
    func body(content: Content) -> some View {
        content
            .opacity(on ? 1 : 0)
            .offset(y: on ? 0 : y)
            .scaleEffect(on ? 1 : 0.97)
            .onAppear { withAnimation(UI.spring.delay(delay)) { on = true } }
    }
}

// MARK: - Buttons

struct IconButton: View {
    var symbol: String
    var help: String
    var size: CGFloat = 30
    var active = false
    var tint: Color = .white
    var action: () -> Void
    @State private var hover = false
    @State private var pressed = false

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: size * 0.45, weight: .semibold))
                .foregroundStyle(active ? tint : tint.opacity(hover ? 1 : 0.78))
                .frame(width: size, height: size)
                .background(Circle().fill(Color.white.opacity(active ? 0.22 : hover ? 0.14 : 0)))
                .contentShape(Circle())
                .scaleEffect(pressed ? 0.86 : hover ? 1.08 : 1)
                .symbolEffectBounce(active)
        }
        .buttonStyle(.plain)
        .help(help)
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
        .simultaneousGesture(DragGesture(minimumDistance: 0)
            .onChanged { _ in withAnimation(UI.snappy) { pressed = true } }
            .onEnded { _ in withAnimation(UI.snappy) { pressed = false } })
    }
}

extension View {
    @ViewBuilder func symbolEffectBounce(_ v: Bool) -> some View {
        if #available(macOS 14.0, *) { self.symbolEffect(.bounce, value: v) } else { self }
    }
}

struct PillButton: View {
    var title: String
    var symbol: String? = nil
    var selected = false
    var action: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let symbol { Image(systemName: symbol).font(.system(size: 11, weight: .semibold)) }
                Text(title).font(.system(size: 12, weight: .medium))
            }
            .foregroundStyle(selected ? .white : UI.dim)
            .padding(.horizontal, 11).padding(.vertical, 6)
            .chip(14, hover: hover, selected: selected)
            .scaleEffect(hover ? 1.03 : 1)
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
    }
}

struct HoverRow<Content: View>: View {
    var selected = false
    var action: () -> Void
    @ViewBuilder var content: (Bool) -> Content
    @State private var hover = false
    var body: some View {
        Button(action: action) {
            content(hover)
                .padding(.horizontal, 10).padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.white.opacity(selected ? 0.16 : hover ? 0.09 : 0)))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(UI.soft) { hover = h } }
    }
}

// MARK: - The orb (Glass's "face")

enum OrbState { case idle, thinking, listening, speaking }

struct Orb: View {
    var size: CGFloat
    var state: OrbState = .idle
    var level: Float = 0

    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            let speed: Double = state == .thinking ? 2.6 : state == .idle ? 0.5 : 1.4
            let breathe = state == .listening ? 1 + Double(level) * 0.22 : 1 + 0.045 * sin(t * (state == .thinking ? 5 : 1.6))
            ZStack {
                Circle()
                    .fill(AngularGradient(colors: colors + [colors[0]], center: .center, angle: .degrees(t * 40 * speed)))
                    .blur(radius: size * 0.08)
                Circle()
                    .fill(RadialGradient(colors: [.white.opacity(0.75), .clear], center: UnitPoint(x: 0.35, y: 0.28),
                                         startRadius: 0, endRadius: size * 0.45))
                Circle().strokeBorder(Color.white.opacity(0.55), lineWidth: max(0.6, size * 0.025))
            }
            .frame(width: size, height: size)
            .scaleEffect(breathe)
            .shadow(color: colors[1].opacity(state == .idle ? 0.35 : 0.7), radius: size * (state == .idle ? 0.25 : 0.45))
        }
        .frame(width: size, height: size)
    }

    private var colors: [Color] {
        switch state {
        case .listening: return [Color(hex: "#FF6B6B")!, Color(hex: "#FF9F7A")!, Color(hex: "#FF4F9A")!]
        case .speaking: return [Color(hex: "#6BFFC8")!, Color(hex: "#7AD7FF")!, Color(hex: "#A98BFF")!]
        default: return [Color(hex: "#8FE3FF")!, Color(hex: "#A98BFF")!, Color(hex: "#FF9ED8")!]
        }
    }
}

// MARK: - Activity indicators

struct ThinkingDots: View {
    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            HStack(spacing: 5) {
                ForEach(0..<3) { i in
                    let p = sin(t * 6 - Double(i) * 0.7)
                    Circle().fill(Color.white.opacity(0.55 + 0.4 * p))
                        .frame(width: 6, height: 6)
                        .offset(y: -3 * max(0, p))
                }
            }
        }
    }
}

/// Text with a light sweep moving across it.
struct Shimmer: View {
    var text: String
    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.8) / 1.8
            Text(text)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(UI.faint)
                .overlay(
                    LinearGradient(colors: [.clear, .white, .clear], startPoint: .leading, endPoint: .trailing)
                        .frame(width: 60)
                        .offset(x: CGFloat(t) * 220 - 90)
                        .mask(Text(text).font(.system(size: 13, weight: .medium)))
                )
        }
    }
}

struct VoiceBars: View {
    var level: Float
    var color: Color = .white
    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            HStack(spacing: 3) {
                ForEach(0..<14) { i in
                    let wobble = 0.5 + 0.5 * sin(t * 9 + Double(i) * 0.9)
                    let h = 4 + CGFloat(level) * 22 * CGFloat(0.35 + 0.65 * wobble)
                    Capsule().fill(color.opacity(0.85)).frame(width: 3, height: h)
                }
            }
            .frame(height: 28)
            .animation(.easeOut(duration: 0.08), value: level)
        }
    }
}

struct Toast: View {
    var text: String
    var body: some View {
        Text(text)
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(Capsule().fill(Color.black.opacity(0.55)))
            .overlay(Capsule().strokeBorder(Color.white.opacity(0.18)))
            .shadow(color: .black.opacity(0.3), radius: 12, y: 4)
    }
}

// MARK: - Markdown

/// Block-level Markdown: headings, lists, quotes, rules, and code blocks with a copy button.
/// Inline styling (bold, italic, code, links) comes from AttributedString.
struct MarkdownView: View {
    var text: String
    var streaming = false

    enum Block: Hashable { case para(String), heading(String, Int), bullet(String, Int, String), quote(String), code(String, String), rule }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(MarkdownView.parse(text + (streaming ? " ▍" : "")).enumerated()), id: \.offset) { _, b in
                block(b)
            }
        }
        .textSelection(.enabled)
    }

    @ViewBuilder private func block(_ b: Block) -> some View {
        switch b {
        case .para(let s):
            inline(s).font(.system(size: 13.5)).lineSpacing(3)
        case .heading(let s, let level):
            inline(s).font(.system(size: level == 1 ? 18 : level == 2 ? 16 : 14.5, weight: .bold)).padding(.top, 4)
        case .bullet(let s, let indent, let mark):
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Text(mark).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(UI.dim)
                inline(s).font(.system(size: 13.5)).lineSpacing(3)
            }
            .padding(.leading, CGFloat(indent) * 14)
        case .quote(let s):
            HStack(spacing: 10) {
                Capsule().fill(UI.accent).frame(width: 3)
                inline(s).font(.system(size: 13.5)).foregroundStyle(UI.dim)
            }
        case .code(let lang, let code):
            CodeBlock(lang: lang, code: code)
        case .rule:
            Rectangle().fill(UI.hair).frame(height: 1).padding(.vertical, 4)
        }
    }

    private func inline(_ s: String) -> Text {
        let opts = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        if let a = try? AttributedString(markdown: s, options: opts) { return Text(a) }
        return Text(s)
    }

    static func parse(_ md: String) -> [Block] {
        var out: [Block] = []
        var para: [String] = []
        var code: [String]? = nil
        var lang = ""
        func flush() { if !para.isEmpty { out.append(.para(para.joined(separator: "\n"))); para = [] } }

        for raw in md.components(separatedBy: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if code != nil { out.append(.code(lang, code!.joined(separator: "\n"))); code = nil }
                else { flush(); code = []; lang = String(line.dropFirst(3)) }
                continue
            }
            if code != nil { code!.append(raw); continue }
            if line.isEmpty { flush(); continue }
            let indent = (raw.prefix { $0 == " " }.count) / 2
            if line.hasPrefix("#") {
                let n = line.prefix { $0 == "#" }.count
                if n <= 6, line.dropFirst(n).hasPrefix(" ") { flush(); out.append(.heading(String(line.dropFirst(n + 1)), n)); continue }
            }
            if line == "---" || line == "***" || line == "___" { flush(); out.append(.rule); continue }
            if line.hasPrefix("> ") { flush(); out.append(.quote(String(line.dropFirst(2)))); continue }
            if line.hasPrefix("- [ ] ") || line.hasPrefix("- [x] ") || line.hasPrefix("- [X] ") {
                flush(); out.append(.bullet(String(line.dropFirst(6)), indent, line.hasPrefix("- [ ]") ? "☐" : "☑")); continue
            }
            if line.hasPrefix("- ") || line.hasPrefix("* ") || line.hasPrefix("+ ") {
                flush(); out.append(.bullet(String(line.dropFirst(2)), indent, "•")); continue
            }
            if let r = line.range(of: #"^\d+[.)] "#, options: .regularExpression) {
                flush(); out.append(.bullet(String(line[r.upperBound...]), indent, String(line[r]).trimmingCharacters(in: .whitespaces))); continue
            }
            para.append(line)
        }
        if let code { out.append(.code(lang, code.joined(separator: "\n"))) }
        flush()
        return out
    }
}

struct CodeBlock: View {
    var lang: String
    var code: String
    @State private var copied = false
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(lang.isEmpty ? "code" : lang).font(.system(size: 11, weight: .medium)).foregroundStyle(UI.faint)
                Spacer()
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(code, forType: .string)
                    withAnimation(UI.snappy) { copied = true }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { withAnimation(UI.soft) { copied = false } }
                } label: {
                    Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 11, weight: .medium)).foregroundStyle(copied ? .green : UI.dim)
                        .contentTransition(.symbolEffectIfAvailable)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(Color.white.opacity(0.05))
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code).font(.system(size: 12, design: .monospaced)).foregroundStyle(.white.opacity(0.92))
                    .padding(12)
            }
        }
        .background(Color.black.opacity(0.32))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(UI.hair))
    }
}

extension ContentTransition {
    static var symbolEffectIfAvailable: ContentTransition {
        if #available(macOS 14.0, *) { return .symbolEffect(.replace) }
        return .opacity
    }
}

// MARK: - Attachments

struct AttachmentChip: View {
    var a: Attachment
    var onRemove: (() -> Void)? = nil
    var large = false
    @State private var hover = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Group {
                if let img = a.thumbnail {
                    Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
                        .frame(width: large ? 180 : 56, height: large ? 120 : 56)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                } else {
                    HStack(spacing: 8) {
                        Image(systemName: a.kind == "pdf" ? "doc.richtext" : "doc.text")
                            .font(.system(size: 16)).foregroundStyle(UI.accent)
                            .frame(width: 30, height: 30)
                            .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.1)))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(a.name).font(.system(size: 12, weight: .medium)).lineLimit(1)
                            Text("\(a.kind.uppercased()) · \(Attachments.sizeText(a.bytes))").font(.system(size: 10.5)).foregroundStyle(UI.faint)
                        }
                    }
                    .padding(.horizontal, 10).frame(height: 56).frame(maxWidth: 190)
                    .chip(12)
                }
            }
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(UI.hair))
            .scaleEffect(hover ? 1.03 : 1)

            if let onRemove {
                Button(action: onRemove) {
                    Image(systemName: "xmark").font(.system(size: 8, weight: .bold))
                        .frame(width: 18, height: 18)
                        .background(Circle().fill(Color.black.opacity(0.75)))
                        .overlay(Circle().strokeBorder(Color.white.opacity(0.3)))
                }
                .buttonStyle(.plain)
                .offset(x: 6, y: -6)
                .opacity(hover ? 1 : 0.0001)
            }
        }
        .onHover { h in withAnimation(UI.snappy) { hover = h } }
        .help(a.name)
    }
}
