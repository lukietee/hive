import AppKit
import SwiftUI

// MARK: - Panel

@MainActor
final class NotchPanelController {
    static let panelSize = CGSize(width: 640, height: 460)

    private(set) var panel: NSPanel
    private let store: HiveStore
    private var notchSize: CGSize = .zero
    private var trackTimer: Timer?
    private var leaveWork: DispatchWorkItem?

    init(store: HiveStore) {
        self.store = store
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.isMovable = false
        panel.isFloatingPanel = true
        panel.becomesKeyOnlyIfNeeded = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        // Click-through except over the visible notch shape (see track()).
        panel.ignoresMouseEvents = true
        panel.level = NSWindow.Level(rawValue: NSWindow.Level.mainMenu.rawValue + 3)
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        layout()
        startTracking()
    }

    /// (Re)positions the panel at the top-center of the notch screen.
    func layout() {
        let screen = ScreenGeometry.notchScreen
        let size = Self.panelSize
        let frame = NSRect(x: screen.frame.midX - size.width / 2,
                           y: screen.frame.maxY - size.height,
                           width: size.width, height: size.height)
        notchSize = ScreenGeometry.notchSize(on: screen)
        let host = FirstMouseHostingView(rootView: NotchView(store: store, notchSize: notchSize))
        host.frame = NSRect(origin: .zero, size: size)
        panel.contentView = host
        panel.setFrame(frame, display: true)
    }

    func show() {
        panel.orderFrontRegardless()
    }

    // MARK: Hit-testing

    /// The panel window is 640×460 but mostly transparent. Poll the pointer and only accept
    /// mouse events while it is over the visible shape, so the menu bar and apps underneath
    /// keep working. Hovering also drives the idle → peek expansion.
    private func startTracking() {
        trackTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.track() }
        }
    }

    /// Visible notch shape in AppKit global coordinates.
    private var visibleRect: NSRect {
        let size = NotchLayout.size(store: store, notch: notchSize)
        let f = panel.frame
        return NSRect(x: f.midX - size.width / 2, y: f.maxY - size.height,
                      width: size.width, height: size.height)
    }

    private func track() {
        let inside = visibleRect.insetBy(dx: -6, dy: -6).contains(NSEvent.mouseLocation)
        if panel.ignoresMouseEvents == inside { panel.ignoresMouseEvents = !inside }
        if inside {
            leaveWork?.cancel()
            leaveWork = nil
            if !store.hovering { store.hovering = true }
        } else if store.hovering, leaveWork == nil {
            // Small grace period so the island doesn't flicker shut when the pointer grazes the edge.
            let work = DispatchWorkItem { [weak self] in
                MainActor.assumeIsolated {
                    self?.store.hovering = false
                    self?.leaveWork = nil
                }
            }
            leaveWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35, execute: work)
        }
    }
}

/// Buttons should work on the first click even though the panel never becomes key.
final class FirstMouseHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

// MARK: - Layout

/// Fixed metrics shared by drawing and hit-testing, so clicks land exactly on what's drawn.
enum NotchMetrics {
    static let flare: CGFloat = 10            // concave top corners that melt into the menu bar
    static let expandedWidth: CGFloat = 560
    static let hPad: CGFloat = 20
    static let topGap: CGFloat = 10           // below the hardware notch
    static let bottomPad: CGFloat = 16
    static let header: CGFloat = 26
    static let section: CGFloat = 12
    static let row: CGFloat = 46
    static let rowGap: CGFloat = 8
    static let question: CGFloat = 116
    static let chat: CGFloat = 18
    static let summaryHeader: CGFloat = 30
    static let summaryLine: CGFloat = 24
    static let peekRow: CGFloat = 34

    static func gridHeight(agents n: Int) -> CGFloat {
        let rows = CGFloat((n + 1) / 2)
        return rows == 0 ? 0 : rows * row + (rows - 1) * rowGap
    }
}

@MainActor
enum NotchLayout {
    static func size(store: HiveStore, notch: CGSize) -> CGSize {
        let M = NotchMetrics.self
        let maxH = NotchPanelController.panelSize.height
        let top = notch.height + M.topGap
        switch store.notchMode {
        case .idle:
            return CGSize(width: notch.width + 2 * M.flare, height: notch.height)
        case .peek:
            return CGSize(width: max(notch.width + 240, 420), height: top + M.peekRow + M.bottomPad)
        case .expanded:
            var h = top + M.header
            let n = store.visibleAgents.count
            if n > 0 { h += M.section + M.gridHeight(agents: n) }
            if store.question != nil { h += M.section + M.question }
            if store.lastChat != nil { h += M.section + M.chat }
            return CGSize(width: M.expandedWidth, height: min(h + M.bottomPad, maxH))
        case .summary:
            let lines = CGFloat(min(store.summary?.lines.count ?? 0, 6))
            let h = top + M.summaryHeader + (lines > 0 ? M.section + lines * M.summaryLine : 0) + M.bottomPad
            return CGSize(width: M.expandedWidth, height: min(h, maxH))
        }
    }
}

// MARK: - Shape

/// Island shape: concave flares at the top corners (so it grows out of the menu bar like the
/// hardware notch does) and large continuous-looking bottom corners.
struct NotchShape: Shape {
    var bottomRadius: CGFloat
    var flare: CGFloat = NotchMetrics.flare

    var animatableData: CGFloat {
        get { bottomRadius }
        set { bottomRadius = newValue }
    }

    func path(in rect: CGRect) -> Path {
        let f = min(flare, rect.width / 4)
        let inner = rect.insetBy(dx: f, dy: 0)
        let r = min(bottomRadius, inner.height / 2, inner.width / 2)
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.minY))
        p.addQuadCurve(to: CGPoint(x: inner.minX, y: rect.minY + f), control: CGPoint(x: inner.minX, y: rect.minY))
        p.addLine(to: CGPoint(x: inner.minX, y: inner.maxY - r))
        p.addCurve(to: CGPoint(x: inner.minX + r, y: inner.maxY),
                   control1: CGPoint(x: inner.minX, y: inner.maxY - r * 0.45),
                   control2: CGPoint(x: inner.minX + r * 0.45, y: inner.maxY))
        p.addLine(to: CGPoint(x: inner.maxX - r, y: inner.maxY))
        p.addCurve(to: CGPoint(x: inner.maxX, y: inner.maxY - r),
                   control1: CGPoint(x: inner.maxX - r * 0.45, y: inner.maxY),
                   control2: CGPoint(x: inner.maxX, y: inner.maxY - r * 0.45))
        p.addLine(to: CGPoint(x: inner.maxX, y: rect.minY + f))
        p.addQuadCurve(to: CGPoint(x: rect.maxX, y: rect.minY), control: CGPoint(x: inner.maxX, y: rect.minY))
        p.closeSubpath()
        return p
    }
}

// MARK: - Style tokens

enum HiveStyle {
    static let primary = Color.white
    static let secondary = Color.white.opacity(0.56)
    static let tertiary = Color.white.opacity(0.32)
    static let fill = Color.white.opacity(0.07)
    static let fillHover = Color.white.opacity(0.12)
    static let hairline = Color.white.opacity(0.07)
    static let spring = Animation.spring(response: 0.42, dampingFraction: 0.84)
    static let amber = LinearGradient(colors: [Color(red: 1, green: 0.84, blue: 0.2), Color(red: 1, green: 0.62, blue: 0.04)],
                                      startPoint: .top, endPoint: .bottom)
}

// MARK: - Root view

struct NotchView: View {
    @ObservedObject var store: HiveStore
    let notchSize: CGSize

    private var mode: NotchMode { store.notchMode }
    private var size: CGSize { NotchLayout.size(store: store, notch: notchSize) }

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .top) {
                NotchShape(bottomRadius: mode == .idle ? 12 : 30)
                    .fill(Color.black)
                    .shadow(color: .black.opacity(mode == .idle ? 0 : 0.5), radius: 20, y: 8)

                if mode != .idle {
                    content
                        .padding(.top, notchSize.height + NotchMetrics.topGap)
                        .padding(.horizontal, NotchMetrics.flare + NotchMetrics.hPad)
                        .padding(.bottom, NotchMetrics.bottomPad)
                        .frame(maxHeight: .infinity, alignment: .top)
                        .transition(.opacity.combined(with: .scale(scale: 0.96, anchor: .top)))
                }
            }
            .frame(width: size.width, height: size.height)
            .clipShape(NotchShape(bottomRadius: mode == .idle ? 12 : 30))
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .animation(HiveStyle.spring, value: mode)
        .animation(HiveStyle.spring, value: store.visibleAgents.count)
        .animation(HiveStyle.spring, value: store.question != nil)
        .animation(HiveStyle.spring, value: store.lastChat != nil)
        .environment(\.colorScheme, .dark)
    }

    @ViewBuilder
    private var content: some View {
        switch mode {
        case .summary: summaryCard
        case .peek: peekContent
        default: expandedContent
        }
    }

    // MARK: Peek (idle + hover)

    private var peekContent: some View {
        HStack(spacing: 10) {
            HiveMark(size: 26)
            VStack(alignment: .leading, spacing: 1) {
                Text("Hive")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(HiveStyle.primary)
                HStack(spacing: 5) {
                    Circle()
                        .fill(store.connected ? Color.green : Color.white.opacity(0.3))
                        .frame(width: 5, height: 5)
                    Text(store.connected ? "Ready · Pitch in 5" : "Engine offline")
                        .font(.system(size: 11))
                        .foregroundStyle(HiveStyle.secondary)
                }
            }
            Spacer(minLength: 8)
            Button {
                // ⌥-click starts the short test scenario instead of the real demo.
                let alt = NSEvent.modifierFlags.contains(.option)
                store.start(alt ? "demo_sim" : "pitch_in_5")
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "play.fill").font(.system(size: 10, weight: .bold))
                    Text("Start").font(.system(size: 12, weight: .semibold))
                }
                .padding(.horizontal, 14)
                .frame(height: 28)
                .background(Capsule().fill(Color.white))
                .foregroundStyle(Color.black)
            }
            .buttonStyle(PressableStyle())
            .help("Start Pitch in 5 (⌥-click: demo_sim)")
        }
        .frame(height: NotchMetrics.peekRow)
    }

    // MARK: Expanded

    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: NotchMetrics.section) {
            header.frame(height: NotchMetrics.header)

            if !store.visibleAgents.isEmpty {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: NotchMetrics.rowGap),
                                    GridItem(.flexible(), spacing: NotchMetrics.rowGap)],
                          spacing: NotchMetrics.rowGap) {
                    ForEach(store.visibleAgents) { agent in
                        Button { store.togglePause(agent.id) } label: {
                            AgentRow(agent: agent, paused: store.isPaused(agent.id))
                        }
                        .buttonStyle(PressableStyle())
                        .help(store.isPaused(agent.id) ? "Resume \(agent.name)" : "Pause \(agent.name)")
                        .transition(.scale(scale: 0.85).combined(with: .opacity))
                    }
                }
            }

            if let q = store.question {
                QuestionCard(question: q) { store.answer($0) }
                    .frame(height: NotchMetrics.question)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }

            if let chat = store.lastChat {
                ChatTicker(line: chat)
                    .frame(height: NotchMetrics.chat)
                    .transition(.opacity)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            HiveMark(size: 22)
            Text("Hive")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(HiveStyle.primary)
            if !store.visibleAgents.isEmpty {
                Text("\(store.visibleAgents.count) agents")
                    .font(.system(size: 12))
                    .foregroundStyle(HiveStyle.secondary)
                    .contentTransition(.numericText())
            }

            Spacer()

            if let budget = store.budget {
                BudgetBar(budget: budget)
            }

            if let s = store.countdown {
                HStack(spacing: 4) {
                    Image(systemName: "timer").font(.system(size: 11, weight: .semibold))
                    Text(String(format: "%d:%02d", s / 60, s % 60))
                        .font(.system(size: 15, weight: .semibold).monospacedDigit())
                        .contentTransition(.numericText(countsDown: true))
                }
                .foregroundStyle(s <= 30 ? Color.red : HiveStyle.primary)
            }

            if !store.visibleAgents.isEmpty {
                Button { store.togglePauseAll() } label: {
                    Image(systemName: store.anyPaused ? "play.fill" : "pause.fill")
                        .font(.system(size: 10, weight: .bold))
                        .frame(width: 26, height: 26)
                        .background(Circle().fill(store.anyPaused ? Color.white : HiveStyle.fillHover))
                        .foregroundStyle(store.anyPaused ? Color.black : HiveStyle.primary)
                }
                .buttonStyle(PressableStyle())
                .help(store.anyPaused ? "Resume all agents" : "Pause all agents")
            }
        }
    }

    // MARK: Summary

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: NotchMetrics.section) {
            HStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(Color.black, Color.green)
                    .font(.system(size: 22))
                Text(store.summary?.title ?? "")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(HiveStyle.primary)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Button { store.dismissSummary() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .bold))
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(HiveStyle.fillHover))
                        .foregroundStyle(HiveStyle.secondary)
                }
                .buttonStyle(PressableStyle())
                .help("Dismiss")
            }
            .frame(height: NotchMetrics.summaryHeader)

            let lines = Array((store.summary?.lines ?? []).prefix(6))
            if !lines.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                        SummaryLine(text: line).frame(height: NotchMetrics.summaryLine)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Components

/// Brand mark: an amber hexagon.
struct HiveMark: View {
    var size: CGFloat = 22

    var body: some View {
        Image(systemName: "hexagon.fill")
            .font(.system(size: size * 0.82, weight: .semibold))
            .foregroundStyle(HiveStyle.amber)
            .frame(width: size, height: size)
    }
}

/// Agent badge: SF Symbol on the agent's color, with an optional progress ring around it.
struct AgentBadge: View {
    let color: Color
    let onColor: Color
    let symbol: String
    var size: CGFloat = 30
    var progress: Double? = nil
    var dimmed = false
    var overlaySymbol: String? = nil

    var body: some View {
        ZStack {
            if let progress {
                Circle().stroke(Color.white.opacity(0.1), lineWidth: 2)
                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(color, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
            Circle()
                .fill(LinearGradient(colors: [color.opacity(dimmed ? 0.35 : 1), color.opacity(dimmed ? 0.25 : 0.82)],
                                     startPoint: .top, endPoint: .bottom))
                .padding(progress == nil ? 0 : 4)
            Image(systemName: overlaySymbol ?? symbol)
                .font(.system(size: size * 0.36, weight: .semibold))
                .foregroundStyle(dimmed ? Color.white.opacity(0.8) : onColor)
                .contentTransition(.symbolEffect(.replace))
        }
        .frame(width: size, height: size)
    }
}

struct AgentRow: View {
    let agent: AgentState
    var paused = false
    @State private var hovered = false

    private var statusText: String {
        if paused { return "Paused" }
        if agent.needsHuman { return "Needs your input" }
        return agent.status.isEmpty ? "Starting…" : agent.status
    }

    var body: some View {
        HStack(spacing: 10) {
            AgentBadge(color: agent.color, onColor: agent.onColor, symbol: agent.symbol, size: 34,
                       progress: agent.progress ?? 0, dimmed: paused,
                       overlaySymbol: paused ? "pause.fill" : (hovered ? "pause.fill" : nil))
            VStack(alignment: .leading, spacing: 2) {
                Text(agent.name)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(HiveStyle.primary)
                Text(statusText)
                    .font(.system(size: 11))
                    .foregroundStyle(agent.needsHuman && !paused ? agent.color : HiveStyle.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            Spacer(minLength: 0)
            if agent.needsHuman && !paused {
                Circle().fill(agent.color).frame(width: 6, height: 6)
            }
        }
        .padding(.horizontal, 6)
        .padding(.trailing, 4)
        .frame(height: NotchMetrics.row)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(hovered ? HiveStyle.fillHover : HiveStyle.fill))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(agent.needsHuman && !paused ? agent.color.opacity(0.5) : HiveStyle.hairline, lineWidth: 1))
        .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .onHover { hovered = $0 }
    }
}

/// needs_human: a notification-style card with one button per option.
struct QuestionCard: View {
    let question: HumanQuestion
    let onAnswer: (String) -> Void

    private var style: AgentStyle { AgentPalette.style(for: question.agent) }
    private var rgb: RGB { RGB(hex: style.hex) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                AgentBadge(color: rgb.color, onColor: rgb.onColor, symbol: style.symbol, size: 18)
                Text(style.name.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundStyle(HiveStyle.secondary)
                Text("needs your input")
                    .font(.system(size: 10))
                    .foregroundStyle(HiveStyle.tertiary)
                Spacer()
            }
            Text(question.question)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(HiveStyle.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            HStack(spacing: 8) {
                ForEach(Array(question.options.enumerated()), id: \.offset) { i, opt in
                    Button { onAnswer(opt) } label: {
                        Text(opt)
                            .font(.system(size: 12, weight: .semibold))
                            .lineLimit(1)
                            .frame(maxWidth: .infinity)
                            .frame(height: 30)
                    }
                    .buttonStyle(OptionButtonStyle(prominent: i == 0, tint: rgb.color, onTint: rgb.onColor))
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(HiveStyle.fill))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(HiveStyle.hairline, lineWidth: 1))
    }
}

struct ChatTicker: View {
    let line: ChatLine

    var body: some View {
        let style = AgentPalette.style(for: line.agent.isEmpty ? "conductor" : line.agent)
        let rgb = RGB(hex: style.hex)
        HStack(spacing: 7) {
            AgentBadge(color: rgb.color, onColor: rgb.onColor, symbol: style.symbol, size: 16)
            Text(style.name)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(HiveStyle.primary)
            Text(line.text)
                .font(.system(size: 11))
                .foregroundStyle(HiveStyle.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer(minLength: 0)
        }
    }
}

struct SummaryLine: View {
    let text: String

    var body: some View {
        HStack(spacing: 9) {
            if let m = AgentPalette.match(line: text) {
                let rgb = RGB(hex: m.style.hex)
                AgentBadge(color: rgb.color, onColor: rgb.onColor, symbol: m.style.symbol, size: 18)
                Text(m.style.name)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(HiveStyle.primary)
                    .frame(width: 62, alignment: .leading)
                Text(m.rest)
                    .font(.system(size: 12))
                    .foregroundStyle(HiveStyle.secondary)
                    .lineLimit(1)
            } else {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color.green)
                    .frame(width: 18)
                Text(text)
                    .font(.system(size: 12))
                    .foregroundStyle(HiveStyle.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
    }
}

/// Slight shrink on press, Dynamic Island style.
struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.65), value: configuration.isPressed)
    }
}

/// needs_human option button: the first option is tinted with the agent color, the rest are glass.
struct OptionButtonStyle: ButtonStyle {
    var prominent: Bool
    var tint: Color
    var onTint: Color
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(prominent ? onTint : HiveStyle.primary)
            .background(Capsule().fill(prominent ? tint.opacity(hovered ? 0.92 : 1)
                                                 : (hovered ? Color.white.opacity(0.2) : Color.white.opacity(0.12))))
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.65), value: configuration.isPressed)
            .onHover { hovered = $0 }
    }
}

struct BudgetBar: View {
    let budget: Budget

    private var fraction: Double {
        budget.total > 0 ? min(budget.spent / budget.total, 1) : 0
    }

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: "creditcard.fill")
                .font(.system(size: 11))
                .foregroundStyle(HiveStyle.secondary)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.12))
                Capsule()
                    .fill(fraction > 0.9 ? Color.orange : Color.green)
                    .frame(width: 80 * fraction)
            }
            .frame(width: 80, height: 5)
            Text(String(format: "$%.0f of $%.0f", budget.spent, budget.total))
                .font(.system(size: 11, weight: .medium).monospacedDigit())
                .foregroundStyle(HiveStyle.secondary)
        }
    }
}
