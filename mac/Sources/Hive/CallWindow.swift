import AppKit
import Combine
import SwiftUI

// MARK: - Model

/// State of the current phone call, fed by the call_* events (docs/CONTRACT.md, "Calls").
@MainActor
final class CallModel: ObservableObject {
    enum Phase: Equatable { case dialing, ringing, connected, ended }

    struct Bubble: Identifiable, Equatable {
        let id = UUID()
        var speaker: String   // "agent" | "them"
        var text: String
        var final: Bool
    }

    @Published var visible = false
    @Published var callId = ""
    @Published var agent = ""
    @Published var label = ""
    @Published var to = ""
    @Published var mode = "live"
    @Published var phase: Phase = .dialing
    @Published var connectedAt: Date?
    @Published var endedDuration: Int?
    @Published var bubbles: [Bubble] = []
    @Published var summary = ""
    @Published var outcome = "unknown"
    @Published var details: [(String, String)] = []
    /// Who spoke last and when, for the waveform.
    @Published var speaker = ""
    @Published var spokeAt = Date.distantPast

    private var hideWork: DispatchWorkItem?

    func reset() {
        hideWork?.cancel()
        visible = false
        bubbles = []
    }

    /// HIVE_CALL_DEBUG=1 logs call events to stderr (the window can't be screenshotted without
    /// Screen Recording permission).
    private static let debug = ProcessInfo.processInfo.environment["HIVE_CALL_DEBUG"] != nil

    func handle(_ type: String, agent agentId: String, _ d: [String: Any]) {
        let id = (d["call_id"] as? String) ?? ""
        if Self.debug, type != "call_transcript" || (d["final"] as? Bool) == true {
            let what = d["state"] ?? d["label"] ?? d["outcome"] ?? d["speaker"] ?? ""
            FileHandle.standardError.write(Data("[call] \(type) \(agentId) \(what)\n".utf8))
        }
        if type != "call_started", !callId.isEmpty, !id.isEmpty, id != callId { return }
        switch type {
        case "call_started":
            hideWork?.cancel()
            callId = id
            agent = agentId
            label = CleanText.strip((d["label"] as? String) ?? "Call")
            to = (d["to"] as? String) ?? ""
            mode = (d["mode"] as? String) ?? "live"
            phase = .dialing
            connectedAt = nil
            endedDuration = nil
            bubbles = []
            summary = ""
            outcome = "unknown"
            details = []
            speaker = ""
            withAnimation(HiveStyle.spring) { visible = true }
        case "call_state":
            switch d["state"] as? String {
            case "ringing": phase = .ringing
            case "connected":
                phase = .connected
                if connectedAt == nil { connectedAt = Date() }
            case "ended": phase = .ended
            default: break
            }
        case "call_transcript":
            guard let text = d["text"] as? String, !text.isEmpty else { return }
            let who = (d["speaker"] as? String) == "agent" ? "agent" : "them"
            let final = (d["final"] as? Bool) ?? true
            if phase != .connected, phase != .ended {
                phase = .connected
                connectedAt = connectedAt ?? Date()
            }
            withAnimation(.easeOut(duration: 0.18)) {
                if let last = bubbles.indices.last, bubbles[last].speaker == who, !bubbles[last].final {
                    bubbles[last].text = text
                    bubbles[last].final = final
                } else {
                    bubbles.append(Bubble(speaker: who, text: text, final: final))
                }
            }
            speaker = who
            spokeAt = Date()
        case "call_ended":
            withAnimation(HiveStyle.spring) {
                phase = .ended
                endedDuration = (d["duration_s"] as? NSNumber)?.intValue
                summary = CleanText.strip((d["summary"] as? String) ?? "")
                outcome = (d["outcome"] as? String) ?? "unknown"
                details = Self.chips(d["details"] as? [String: Any] ?? [:])
                bubbles = bubbles.map { var b = $0; b.final = true; return b }
            }
            speaker = ""
            let work = DispatchWorkItem { [weak self] in
                withAnimation(HiveStyle.spring) { self?.visible = false }
            }
            hideWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 9, execute: work)
        default:
            break
        }
    }

    /// The few facts worth showing as chips, in a stable order.
    private static func chips(_ d: [String: Any]) -> [(String, String)] {
        let order = ["pickup_time", "price", "writing", "cake", "change", "contact"]
        func fmt(_ k: String, _ v: Any) -> String {
            if k == "price", let n = v as? NSNumber { return String(format: "$%.0f", n.doubleValue) }
            return "\(v)"
        }
        return order.compactMap { k in d[k].map { (k, fmt(k, $0)) } }.prefix(3).map { $0 }
    }

    var formattedNumber: String {
        let digits = to.filter(\.isNumber)
        if to.hasPrefix("+1"), digits.count == 11 {
            let d = Array(digits.dropFirst())
            return "+1 (\(String(d[0..<3]))) \(String(d[3..<6]))-\(String(d[6..<10]))"
        }
        return to
    }
}

// MARK: - Window

@MainActor
final class CallWindowController {
    static let size = CGSize(width: 360, height: 580)

    private let model: CallModel
    private var window: NSPanel?
    private var bag = Set<AnyCancellable>()

    init(model: CallModel) {
        self.model = model
        model.$visible
            .removeDuplicates()
            .sink { [weak self] visible in DispatchQueue.main.async { visible ? self?.show() : self?.hide() } }
            .store(in: &bag)
    }

    private func makeWindow() -> NSPanel {
        let p = NSPanel(contentRect: Self.defaultFrame(), styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.level = .floating
        p.isMovableByWindowBackground = true
        p.hidesOnDeactivate = false
        p.isReleasedWhenClosed = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        let host = NSHostingView(rootView: CallView(model: model))
        host.frame = NSRect(origin: .zero, size: Self.size)
        p.contentView = host
        return p
    }

    private func show() {
        let w = window ?? makeWindow()
        window = w
        w.alphaValue = 0
        w.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.25
            w.animator().alphaValue = 1
        }
    }

    private func hide() {
        guard let w = window, w.isVisible else { return }
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.25
            w.animator().alphaValue = 0
        }, completionHandler: {
            MainActor.assumeIsolated { w.orderOut(nil) }
        })
    }

    /// Top-right of the notch screen, under the menu bar, clear of the notch panel.
    static func defaultFrame() -> NSRect {
        let vf = ScreenGeometry.notchScreen.visibleFrame
        return NSRect(x: vf.maxX - size.width - 20, y: vf.maxY - size.height - 16,
                      width: size.width, height: size.height)
    }
}

// MARK: - View

struct CallView: View {
    @ObservedObject var model: CallModel

    private var style: AgentStyle { AgentPalette.style(for: model.agent.isEmpty ? "caller" : model.agent) }
    private var tint: Color { RGB(hex: style.hex).color }

    var body: some View {
        VStack(spacing: 0) {
            topBar
                .padding(.horizontal, 18)
                .padding(.top, 16)
            callerHeader
                .padding(.top, 18)
            CallWaveform(model: model, tint: tint)
                .frame(height: 34)
                .padding(.horizontal, 36)
                .padding(.top, 14)
            transcript
                .padding(.top, 12)
            if model.phase == .ended, !model.summary.isEmpty {
                summaryCard
                    .padding(.horizontal, 14)
                    .padding(.bottom, 14)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(width: CallWindowController.size.width, height: CallWindowController.size.height)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(Color(white: 0.07))
                .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.09), lineWidth: 1))
        )
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .environment(\.colorScheme, .dark)
    }

    private var topBar: some View {
        HStack(spacing: 8) {
            AgentBadge(color: tint, onColor: RGB(hex: style.hex).onColor, symbol: style.symbol, size: 22)
            Text(style.name)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(HiveStyle.primary)
            Text(model.mode == "fake" ? "Simulated call" : "via Photon")
                .font(.system(size: 11))
                .foregroundStyle(HiveStyle.tertiary)
            Spacer()
            HStack(spacing: 5) {
                Circle().fill(Color.red).frame(width: 6, height: 6)
                    .opacity(model.phase == .ended ? 0.35 : 1)
                Text("AI call · Recorded")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(HiveStyle.secondary)
            }
            .padding(.horizontal, 9)
            .frame(height: 22)
            .background(Capsule().fill(Color.white.opacity(0.08)))
        }
    }

    private var callerHeader: some View {
        VStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(LinearGradient(colors: [Color(white: 0.36), Color(white: 0.2)],
                                         startPoint: .top, endPoint: .bottom))
                Image(systemName: "storefront.fill")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(Color.white.opacity(0.92))
            }
            .frame(width: 68, height: 68)
            .overlay(Circle().stroke(tint.opacity(model.phase == .connected ? 0.7 : 0), lineWidth: 2).padding(-4))
            Text(model.label)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(HiveStyle.primary)
                .lineLimit(1)
                .padding(.top, 4)
            Text(model.formattedNumber)
                .font(.system(size: 12).monospacedDigit())
                .foregroundStyle(HiveStyle.secondary)
            statusLine
                .padding(.top, 2)
        }
        .padding(.horizontal, 18)
    }

    @ViewBuilder
    private var statusLine: some View {
        switch model.phase {
        case .dialing:
            Text("Calling…").font(.system(size: 13)).foregroundStyle(HiveStyle.secondary)
        case .ringing:
            Text("Ringing…").font(.system(size: 13)).foregroundStyle(HiveStyle.secondary)
        case .connected:
            TimelineView(.periodic(from: .now, by: 1)) { ctx in
                Text(Self.clock(Int(ctx.date.timeIntervalSince(model.connectedAt ?? ctx.date))))
                    .font(.system(size: 15, weight: .medium).monospacedDigit())
                    .foregroundStyle(HiveStyle.primary)
            }
        case .ended:
            Text("Call ended" + (model.endedDuration.map { " · \(Self.clock($0))" } ?? ""))
                .font(.system(size: 13))
                .foregroundStyle(HiveStyle.secondary)
        }
    }

    static func clock(_ s: Int) -> String { String(format: "%d:%02d", max(0, s) / 60, max(0, s) % 60) }

    /// Newest lines anchored to the bottom; older ones slide up and fade out under the header,
    /// like live captions. (No ScrollView: a call transcript only ever grows at the bottom.)
    private var transcript: some View {
        // An overlay can't grow its parent, so the header never gets pushed off the window.
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay(alignment: .bottom) {
                VStack(spacing: 6) {
                    ForEach(model.bubbles.suffix(14)) { b in
                        TranscriptBubble(bubble: b, tint: tint, theirName: model.label)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 14)
                .padding(.bottom, 10)
            }
            .clipped()
            .mask(LinearGradient(stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.18),
                                     .init(color: .black, location: 1)], startPoint: .top, endPoint: .bottom))
    }

    private var summaryCard: some View {
        let ok = model.outcome == "success"
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: ok ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(Color.black, ok ? Color.green : Color.orange)
                    .font(.system(size: 18))
                Text(ok ? "Done" : "Needs a follow-up")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(HiveStyle.primary)
                Spacer()
            }
            Text(model.summary)
                .font(.system(size: 12))
                .foregroundStyle(HiveStyle.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(4)
            if !model.details.isEmpty {
                HStack(spacing: 6) {
                    ForEach(model.details, id: \.0) { _, v in
                        Text(v)
                            .font(.system(size: 11, weight: .medium))
                            .lineLimit(1)
                            .padding(.horizontal, 9)
                            .frame(height: 22)
                            .background(Capsule().fill(Color.white.opacity(0.1)))
                            .foregroundStyle(HiveStyle.primary)
                    }
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.white.opacity(0.07)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(HiveStyle.hairline, lineWidth: 1))
    }
}

struct TranscriptBubble: View {
    let bubble: CallModel.Bubble
    let tint: Color
    let theirName: String

    private var mine: Bool { bubble.speaker == "agent" }

    var body: some View {
        HStack {
            if mine { Spacer(minLength: 44) }
            Text(bubble.text)
                .font(.system(size: 13))
                .foregroundStyle(HiveStyle.primary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 17, style: .continuous)
                        .fill(mine ? tint.opacity(0.28) : Color.white.opacity(0.1))
                )
                .opacity(bubble.final ? 1 : 0.62)
                .frame(maxWidth: 260, alignment: mine ? .trailing : .leading)
            if !mine { Spacer(minLength: 44) }
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

/// Bars that move while someone is talking: the agent's color for Hive, white for the other side.
struct CallWaveform: View {
    @ObservedObject var model: CallModel
    let tint: Color
    private let bars = 30

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let talking = model.phase == .connected && ctx.date.timeIntervalSince(model.spokeAt) < 1.2
            let color = model.speaker == "agent" ? tint : Color.white.opacity(0.85)
            HStack(alignment: .center, spacing: 3) {
                ForEach(0..<bars, id: \.self) { i in
                    let x = Double(i)
                    let env = sin(.pi * (x + 0.5) / Double(bars))           // taller in the middle
                    let wave = 0.5 + 0.5 * sin(t * 7.3 + x * 0.9) * cos(t * 3.1 + x * 0.37)
                    let h = talking ? 4 + 26 * env * wave : (model.phase == .ended ? 2 : 3 + 1.5 * env)
                    Capsule()
                        .fill(talking ? color : Color.white.opacity(0.22))
                        .frame(width: 3, height: h)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
