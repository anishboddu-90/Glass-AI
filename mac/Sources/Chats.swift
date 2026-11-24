import AppKit
import Foundation

struct ChatMessage: Codable, Identifiable, Equatable {
    var id = UUID()
    var role: String                 // user | assistant
    var content: String
    var attachments: [Attachment] = []
    var provider: String = ""
    var model: String = ""
    var error = false
    var time = Date()

    init(role: String, content: String, attachments: [Attachment] = []) {
        self.role = role
        self.content = content
        self.attachments = attachments
    }
}

struct ChatSession: Codable, Identifiable, Equatable {
    var id = UUID().uuidString
    var title = "New chat"
    var smartTitled = false
    var pinned = false
    var updated = Date()
    var provider = ""
    var model = ""
    var messages: [ChatMessage] = []
}

/// Owns the conversation: sending, streaming, editing, regenerating, titles and persistence.
@MainActor
final class ChatModel: ObservableObject {
    static let shared = ChatModel()

    @Published var sessions: [ChatSession] = []
    @Published var current = ChatSession()
    @Published var streamingID: UUID?
    @Published var draft = ""
    @Published var pending: [Attachment] = []
    @Published var editingIndex: Int?
    @Published var search = ""

    /// Called with the finished reply text (voice mode uses it to speak and listen again).
    var onReplyFinished: ((String) -> Void)?
    var onToast: ((String) -> Void)?

    private var task: Task<Void, Never>?
    private let s = Settings.shared
    private let dir: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let d = base.appendingPathComponent("Glass/chats", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }()

    var isStreaming: Bool { streamingID != nil }
    var isEmpty: Bool { current.messages.isEmpty }

    private init() { loadAll() }

    // MARK: persistence

    private func loadAll() {
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        let files = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
        sessions = files.filter { $0.pathExtension == "json" }.compactMap {
            guard let d = try? Data(contentsOf: $0) else { return nil }
            return try? dec.decode(ChatSession.self, from: d)
        }
        sortSessions()
    }

    private func sortSessions() {
        sessions.sort { a, b in a.pinned != b.pinned ? a.pinned : a.updated > b.updated }
    }

    func persist(touch: Bool = true) {
        guard !current.messages.isEmpty else { return }
        if touch { current.updated = Date() }
        current.provider = s.provider
        current.model = s.model
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601
        if let d = try? enc.encode(current) {
            try? d.write(to: dir.appendingPathComponent(current.id + ".json"), options: .atomic)
        }
        if let i = sessions.firstIndex(where: { $0.id == current.id }) { sessions[i] = current } else { sessions.insert(current, at: 0) }
        sortSessions()
    }

    private func write(_ c: ChatSession) {
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601
        if let d = try? enc.encode(c) { try? d.write(to: dir.appendingPathComponent(c.id + ".json"), options: .atomic) }
    }

    // MARK: sessions

    func newChat() {
        stop()
        current = ChatSession()
        draft = ""; pending = []; editingIndex = nil
    }

    func open(_ id: String) {
        guard id != current.id, let c = sessions.first(where: { $0.id == id }) else { return }
        stop()
        current = c
        editingIndex = nil
        if !c.provider.isEmpty, s.hasKey(c.provider) {
            s.provider = c.provider
            if !c.model.isEmpty { s.model = c.model }
        }
    }

    func delete(_ id: String) {
        try? FileManager.default.removeItem(at: dir.appendingPathComponent(id + ".json"))
        sessions.removeAll { $0.id == id }
        if current.id == id { newChat() }
    }

    func togglePin(_ id: String) {
        guard let i = sessions.firstIndex(where: { $0.id == id }) else { return }
        sessions[i].pinned.toggle()
        if current.id == id { current.pinned = sessions[i].pinned }
        write(sessions[i])
        sortSessions()
    }

    func exportMarkdown(_ id: String) {
        guard let c = sessions.first(where: { $0.id == id }) ?? (current.id == id ? current : nil) else { return }
        var md = "# \(c.title)\n\n"
        for m in c.messages {
            md += m.role == "user" ? "**You**\n\n" : "**\(Settings.label(m.provider.isEmpty ? c.provider : m.provider))**\n\n"
            for a in m.attachments { md += "_Attachment: \(a.name)_\n\n" }
            md += m.content + "\n\n---\n\n"
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(md, forType: .string)
        onToast?("Chat copied as Markdown")
    }

    var filtered: [ChatSession] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return sessions }
        return sessions.filter { c in
            c.title.lowercased().contains(q) || c.messages.contains { $0.content.lowercased().contains(q) }
        }
    }

    /// Pinned / Today / Yesterday / Previous 7 days / Previous 30 days / Older
    var buckets: [(String, [ChatSession])] {
        let cal = Calendar.current
        var order: [String] = []
        var map: [String: [ChatSession]] = [:]
        for c in filtered {
            let b: String
            if c.pinned { b = "Pinned" }
            else if cal.isDateInToday(c.updated) { b = "Today" }
            else if cal.isDateInYesterday(c.updated) { b = "Yesterday" }
            else {
                let days = cal.dateComponents([.day], from: c.updated, to: Date()).day ?? 0
                b = days < 7 ? "Previous 7 days" : days < 30 ? "Previous 30 days" : "Older"
            }
            if map[b] == nil { order.append(b) }
            map[b, default: []].append(c)
        }
        return order.map { ($0, map[$0]!) }
    }

    static func relative(_ d: Date) -> String {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .abbreviated
        return Date().timeIntervalSince(d) < 60 ? "now" : f.localizedString(for: d, relativeTo: Date())
    }

    static func makeTitle(_ text: String) -> String {
        let t = text.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespaces)
        if t.isEmpty { return "New chat" }
        return t.count > 42 ? String(t.prefix(40)).trimmingCharacters(in: .whitespaces) + "…" : t
    }

    // MARK: conversation

    func beginEdit(_ index: Int) {
        guard !isStreaming, current.messages.indices.contains(index), current.messages[index].role == "user" else { return }
        editingIndex = index
        draft = current.messages[index].content
        pending = current.messages[index].attachments
    }

    func editLast() {
        if let i = current.messages.lastIndex(where: { $0.role == "user" }) { beginEdit(i) }
    }

    func cancelEdit() { editingIndex = nil; draft = ""; pending = [] }

    func send(_ textIn: String? = nil) {
        let text = (textIn ?? draft).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !isStreaming, !text.isEmpty || !pending.isEmpty else { return }
        guard s.hasKey(s.provider) else { onToast?("Add an API key in Settings first"); return }
        if let i = editingIndex, i <= current.messages.count {
            current.messages.removeSubrange(i...)
        }
        var m = ChatMessage(role: "user", content: text, attachments: pending)
        m.provider = s.provider; m.model = s.model
        if current.messages.isEmpty {
            current.title = ChatModel.makeTitle(text.isEmpty ? (pending.first?.name ?? "Attachment") : text)
        }
        current.messages.append(m)
        draft = ""; pending = []; editingIndex = nil
        runReply()
    }

    func regenerate() {
        guard !isStreaming else { return }
        if current.messages.last?.role == "assistant" { current.messages.removeLast() }
        guard current.messages.last?.role == "user" else { return }
        runReply()
    }

    func stop() {
        task?.cancel(); task = nil
        if streamingID != nil {
            streamingID = nil
            persist()
        }
    }

    private func runReply() {
        let req = AIRequest(provider: s.provider, model: s.model, baseURL: s.baseURL, key: s.apiKey, system: systemPrompt())
        let history = current.messages
        var reply = ChatMessage(role: "assistant", content: "")
        reply.provider = s.provider; reply.model = s.model
        current.messages.append(reply)
        let id = reply.id
        streamingID = id
        s.rememberModel(s.model)

        task = Task { [weak self] in
            var failure: Error?
            do {
                for try await delta in AI.stream(req, history: history) {
                    guard let self else { return }
                    if let i = self.current.messages.firstIndex(where: { $0.id == id }) {
                        self.current.messages[i].content += delta
                    }
                }
            } catch is CancellationError {
            } catch {
                failure = error
            }
            guard let self, self.streamingID == id else { return }
            self.streamingID = nil
            guard let i = self.current.messages.firstIndex(where: { $0.id == id }) else { return }
            if let e = failure, !Task.isCancelled {
                let msg = e.localizedDescription
                if self.current.messages[i].content.isEmpty {
                    self.current.messages[i].content = msg
                } else {
                    self.current.messages[i].content += "\n\n_\(msg)_"
                }
                self.current.messages[i].error = true
            }
            self.persist()
            let text = self.current.messages[i].content
            if failure == nil {
                self.smartTitle()
                self.onReplyFinished?(text)
            }
        }
    }

    private func systemPrompt() -> String {
        let f = DateFormatter(); f.dateStyle = .full; f.timeStyle = .short
        return s.systemPrompt + "\n\nCurrent date and time: \(f.string(from: Date())). The user is on macOS."
    }

    /// After the first exchange, ask the model for a short title.
    private func smartTitle() {
        guard !current.smartTitled, current.messages.count >= 2 else { return }
        current.smartTitled = true
        let id = current.id
        let first = String(current.messages[0].content.prefix(600))
        let answer = String(current.messages[1].content.prefix(600))
        let req = AIRequest(provider: s.provider, model: s.model, baseURL: s.baseURL, key: s.apiKey, system: "")
        Task { [weak self] in
            let prompt = "Write a 2–5 word title for this chat. Reply with the title only, no quotes or punctuation at the end.\n\nUser: \(first)\n\nAssistant: \(answer)"
            guard let raw = try? await AI.quick(req, prompt: prompt) else { return }
            var t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'`*#.")).components(separatedBy: "\n")[0]
            if t.count > 48 { t = String(t.prefix(46)) + "…" }
            guard let self, !t.isEmpty else { return }
            if self.current.id == id {
                self.current.title = t
                self.persist(touch: false)
            } else if let i = self.sessions.firstIndex(where: { $0.id == id }) {
                self.sessions[i].title = t
                self.write(self.sessions[i])
            }
        }
    }

    func addAttachments(_ list: [Attachment]) {
        let room = max(0, 10 - pending.count)
        pending.append(contentsOf: list.prefix(room))
        if list.count > room { onToast?("Up to 10 attachments per message") }
    }
}
