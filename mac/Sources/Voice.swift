import AVFoundation
import Foundation
import Speech

/// Dictation (on-device when available) plus spoken replies.
@MainActor
final class Voice: NSObject, ObservableObject {
    static let shared = Voice()

    @Published var listening = false
    @Published var partial = ""
    @Published var level: Float = 0          // 0…1, drives the voice bars and orb
    @Published var speaking = false
    @Published var mode = false              // hands-free loop: listen → send → speak → listen

    /// Called with the final transcript after a short pause.
    var onFinal: ((String) -> Void)?
    var onError: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var recTask: SFSpeechRecognitionTask?
    private let recognizer = SFSpeechRecognizer()
    private let synth = AVSpeechSynthesizer()
    private var silence: Timer?

    private override init() {
        super.init()
        synth.delegate = self
    }

    // MARK: listening

    func start() {
        guard !listening else { return }
        stopSpeaking()
        authorize { [weak self] ok, why in
            guard let self else { return }
            guard ok else { self.mode = false; self.onError?(why); return }
            do { try self.begin() } catch {
                self.mode = false
                self.onError?("Couldn't start the microphone: \(error.localizedDescription)")
            }
        }
    }

    private func authorize(_ done: @escaping (Bool, String) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            AVCaptureDevice.requestAccess(for: .audio) { mic in
                DispatchQueue.main.async {
                    if status != .authorized { done(false, "Allow Speech Recognition for Glass in System Settings → Privacy & Security.") }
                    else if !mic { done(false, "Allow Microphone access for Glass in System Settings → Privacy & Security.") }
                    else { done(true, "") }
                }
            }
        }
    }

    private func begin() throws {
        guard let recognizer, recognizer.isAvailable else { throw AIError.message("Speech recognition isn't available right now.") }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        if recognizer.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true }
        req.addsPunctuation = true
        request = req
        partial = ""

        let input = engine.inputNode
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0),
                         block: Voice.tap(req) { [weak self] lvl in self?.level = lvl })
        engine.prepare()
        try engine.start()
        listening = true

        recTask = recognizer.recognitionTask(with: req, resultHandler: Voice.results { [weak self] text, final, failed in
            guard let self, self.listening else { return }
            if let text { self.partial = text; self.armSilence() }
            if final || failed { self.finish() }
        })
        armSilence(first: true)
    }

    // These run on audio / recognizer threads, so they're built outside the main actor.
    nonisolated private static func tap(_ req: SFSpeechAudioBufferRecognitionRequest,
                                        level: @escaping @MainActor (Float) -> Void) -> AVAudioNodeTapBlock {
        return { buf, _ in
            req.append(buf)
            guard let ch = buf.floatChannelData?[0] else { return }
            let n = Int(buf.frameLength)
            var sum: Float = 0
            for i in 0..<n { sum += ch[i] * ch[i] }
            let rms = sqrt(sum / Float(max(n, 1)))
            let v = min(1, max(0, (20 * log10(max(rms, 1e-6)) + 55) / 45))
            DispatchQueue.main.async { level(v) }
        }
    }

    nonisolated private static func results(_ handle: @escaping @MainActor (String?, Bool, Bool) -> Void)
        -> (SFSpeechRecognitionResult?, Error?) -> Void {
        return { result, error in
            let text = result?.bestTranscription.formattedString
            let final = result?.isFinal ?? false
            let failed = error != nil
            DispatchQueue.main.async { handle(text, final, failed) }
        }
    }

    private func armSilence(first: Bool = false) {
        silence?.invalidate()
        // wait longer before anything was said
        silence = Timer.scheduledTimer(withTimeInterval: first ? 6 : 1.3, repeats: false) { [weak self] _ in
            DispatchQueue.main.async { self?.finish() }
        }
    }

    /// Stop listening and deliver what was heard.
    func finish() {
        guard listening else { return }
        let text = partial.trimmingCharacters(in: .whitespacesAndNewlines)
        teardown()
        if text.isEmpty {
            if mode { mode = false }
        } else {
            onFinal?(text)
        }
    }

    /// Stop without sending.
    func cancel() {
        mode = false
        teardown()
        stopSpeaking()
    }

    private func teardown() {
        silence?.invalidate(); silence = nil
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
        request?.endAudio(); request = nil
        recTask?.cancel(); recTask = nil
        listening = false
        level = 0
    }

    // MARK: speaking

    static var voices: [AVSpeechSynthesisVoice] {
        AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.hasPrefix(String(Locale.preferredLanguages.first?.prefix(2) ?? "en")) }
            .sorted { ($0.quality.rawValue, $0.name) > ($1.quality.rawValue, $1.name) }
    }

    func speak(_ markdown: String) {
        let text = Voice.plain(markdown)
        guard !text.isEmpty else { return }
        stopSpeaking()
        let u = AVSpeechUtterance(string: text)
        let id = Settings.shared.voiceID
        u.voice = id.isEmpty ? Voice.voices.first : AVSpeechSynthesisVoice(identifier: id)
        u.rate = AVSpeechUtteranceDefaultSpeechRate * 1.04
        speaking = true
        synth.speak(u)
    }

    func stopSpeaking() {
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
        speaking = false
    }

    /// Markdown → something pleasant to read aloud (code blocks skipped).
    static func plain(_ md: String) -> String {
        var out: [String] = []
        var inCode = false
        for line in md.components(separatedBy: "\n") {
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                if !inCode { out.append("(code omitted)") }
                inCode.toggle(); continue
            }
            if inCode { continue }
            out.append(line)
        }
        var s = out.joined(separator: "\n")
        for (p, r) in [(#"!\[[^\]]*\]\([^)]*\)"#, ""), (#"\[([^\]]+)\]\([^)]*\)"#, "$1"), (#"[*_`#>|~]+"#, ""), (#"^\s*[-+]\s+"#, "")] {
            s = s.replacingOccurrences(of: p, with: r, options: .regularExpression)
        }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

extension Voice: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
        DispatchQueue.main.async { Voice.shared.didFinishSpeaking() }
    }
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) {
        DispatchQueue.main.async { Voice.shared.speaking = false }
    }

    func didFinishSpeaking() {
        speaking = false
        if mode { start() }   // keep the conversation going
    }
}
