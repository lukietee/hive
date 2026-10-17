import AppKit
import SwiftUI

// MARK: - Panel

@MainActor
final class NotchPanelController {
    static let panelSize = CGSize(width: 600, height: 340)

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

    /// The panel window is 600×340 but mostly transparent. Poll the pointer and only accept
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

/// Size of the visible notch shape for the current state. Shared by the view (drawing)
/// and the panel controller (hit-testing), so clicks land exactly on what's drawn.
@MainActor
enum NotchLayout {
    static func size(store: HiveStore, notch: CGSize) -> CGSize {
        let maxH = NotchPanelController.panelSize.height
        switch store.notchMode {
        case .idle:
            return CGSize(width: notch.width + 36, height: notch.height)
        case .peek:
            return CGSize(width: max(notch.width + 200, 380), height: notch.height + 56)
        case .expanded:
            let rows = CGFloat((store.visibleAgents.count + 2) / 3)
            var h = notch.height + 44 + rows * 46
            if store.question != nil { h += 34 }
            if store.lastChat != nil { h += 22 }
            return CGSize(width: 520, height: min(h + 12, maxH))
        case .summary:
            let lines = CGFloat(min(store.summary?.lines.count ?? 0, 6))
            return CGSize(width: 520, height: min(notch.height + 64 + lines * 20, maxH))
        }
    }
}

// MARK: - Shape

/// Flat top (merges with the hardware notch), rounded bottom corners.
struct NotchShape: Shape {
    var bottomRadius: CGFloat

    var animatableData: CGFloat {
        get { bottomRadius }
        set { bottomRadius = newValue }
    }

    func path(in rect: CGRect) -> Path {
        let r = min(bottomRadius, rect.height / 2, rect.width / 2)
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - r))
        p.addQuadCurve(to: CGPoint(x: rect.maxX - r, y: rect.maxY), control: CGPoint(x: rect.maxX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.minX + r, y: rect.maxY))
        p.addQuadCurve(to: CGPoint(x: rect.minX, y: rect.maxY - r), control: CGPoint(x: rect.minX, y: rect.maxY))
        p.closeSubpath()
        return p
    }
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
                NotchShape(bottomRadius: mode == .idle ? 10 : 24)
                    .fill(Color.black)
                    .shadow(color: .black.opacity(mode == .idle ? 0 : 0.45), radius: 14, y: 6)

                if mode == .idle {
                    idleIndicator
                } else {
                    content
                        .padding(.top, notchSize.height + 8)
                        .padding(.horizontal, 18)
                        .padding(.bottom, 12)
                        .transition(.opacity)
                }
            }
            .frame(width: size.width, height: size.height)
            .clipped()
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .animation(.spring(response: 0.45, dampingFraction: 0.78), value: mode)
        .animation(.spring(response: 0.45, dampingFraction: 0.78), value: store.visibleAgents.count)
        .animation(.spring(response: 0.45, dampingFraction: 0.78), value: store.question != nil)
        .preferredColorScheme(.dark)
    }

    /// Tiny status dot peeking out to the right of the hardware notch.
    private var idleIndicator: some View {
        HStack {
            Spacer()
            Circle()
                .fill(store.connected ? Color.green : Color.gray)
                .frame(width: 6, height: 6)
                .padding(.trailing, 9)
        }
        .frame(height: notchSize.height)
    }

    @ViewBuilder
    private var content: some View {
        switch mode {
        case .summary:
            summaryCard
        case .peek:
            peekContent
        default:
            expandedContent
        }
    }

    // MARK: Peek (idle + hover)

    private var peekContent: some View {
        HStack(spacing: 10) {
            Text("🐝 Hive")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundColor(.white)
            Circle()
                .fill(store.connected ? Color.green : Color.gray)
                .frame(width: 6, height: 6)
            Text(store.connected ? "Engine ready" : "Engine offline")
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundColor(.white.opacity(0.55))
            Spacer(minLength: 6)
            Button {
                // ⌥-click starts the short test scenario instead of the real demo.
                let alt = NSEvent.modifierFlags.contains(.option)
                store.start(alt ? "demo_sim" : "pitch_in_5")
            } label: {
                Label("Pitch in 5", systemImage: "play.fill")
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 5)
                    .background(Capsule().fill(Color.white))
                    .foregroundColor(.black)
            }
            .buttonStyle(PressableStyle())
            .help("Start Pitch in 5 (⌥-click: demo_sim)")
        }
    }

    // MARK: Expanded

    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            header

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(store.visibleAgents) { agent in
                    Button { store.togglePause(agent.id) } label: {
                        AgentPill(agent: agent, paused: store.isPaused(agent.id))
                    }
                    .buttonStyle(PressableStyle())
                    .help(store.isPaused(agent.id) ? "Resume \(agent.name)" : "Pause \(agent.name)")
                    .transition(.scale(scale: 0.6).combined(with: .opacity))
                }
            }

            if let q = store.question {
                questionRow(q)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }

            if let chat = store.lastChat {
                let style = AgentPalette.style(for: chat.agent)
                Text("💬 \(style.name): \(chat.text)")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.7))
                    .lineLimit(1)
                    .transition(.opacity)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Text("🐝 Hive")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundColor(.white)
            Text("\(store.visibleAgents.count) agents")
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundColor(.white.opacity(0.55))

            Spacer()

            if let budget = store.budget {
                BudgetBar(budget: budget)
            }

            if let s = store.countdown {
                Text(String(format: "⏱ %d:%02d", s / 60, s % 60))
                    .font(.system(size: 13, weight: .bold, design: .monospaced))
                    .foregroundColor(s <= 30 ? .red : .white)
                    .contentTransition(.numericText())
            }

            if !store.visibleAgents.isEmpty {
                Button { store.togglePauseAll() } label: {
                    Image(systemName: store.anyPaused ? "play.fill" : "pause.fill")
                        .font(.system(size: 10, weight: .bold))
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(Color.white.opacity(store.anyPaused ? 0.9 : 0.14)))
                        .foregroundColor(store.anyPaused ? .black : .white)
                }
                .buttonStyle(PressableStyle())
                .help(store.anyPaused ? "Resume all agents" : "Pause all agents")
            }
        }
    }

    private func questionRow(_ q: HumanQuestion) -> some View {
        let style = AgentPalette.style(for: q.agent)
        let color = RGB(hex: style.hex).color
        return HStack(spacing: 8) {
            Text("❓ \(style.name): \(q.question)")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(1)
            Spacer(minLength: 4)
            ForEach(q.options, id: \.self) { opt in
                Button { store.answer(opt) } label: {
                    Text(opt)
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 3)
                        .background(Capsule().fill(color.opacity(0.001)))
                        .background(Capsule().stroke(color, lineWidth: 1.5))
                        .foregroundColor(color)
                }
                .buttonStyle(OptionButtonStyle(color: color))
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 10).fill(color.opacity(0.16)))
    }

    // MARK: Summary

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal.fill")
                    .foregroundColor(.green)
                    .font(.system(size: 18))
                Text(store.summary?.title ?? "")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Button { store.dismissSummary() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .frame(width: 20, height: 20)
                        .background(Circle().fill(Color.white.opacity(0.14)))
                        .foregroundColor(.white.opacity(0.8))
                }
                .buttonStyle(PressableStyle())
                .help("Dismiss")
            }
            ForEach(Array((store.summary?.lines ?? []).prefix(6).enumerated()), id: \.offset) { _, line in
                Text("✓ \(line)")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Components

struct AgentPill: View {
    let agent: AgentState
    var paused = false
    @State private var hovered = false

    private var statusText: String {
        if paused { return "Paused · tap to resume" }
        if agent.needsHuman { return "Waiting for you…" }
        return agent.status.isEmpty ? "Starting…" : agent.status
    }

    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                Circle().stroke(Color.white.opacity(0.15), lineWidth: 3)
                Circle()
                    .trim(from: 0, to: agent.progress ?? 0)
                    .stroke(agent.color, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                if paused || hovered {
                    Image(systemName: paused ? "play.fill" : "pause.fill")
                        .font(.system(size: 8, weight: .heavy))
                        .foregroundColor(agent.color)
                } else {
                    Circle().fill(agent.color).frame(width: 8, height: 8)
                        .opacity(agent.needsHuman ? 0.4 : 1)
                }
            }
            .frame(width: 22, height: 22)

            VStack(alignment: .leading, spacing: 1) {
                Text(agent.name)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
                Text(statusText)
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundColor(agent.needsHuman && !paused ? agent.color : .white.opacity(0.6))
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: 38)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(hovered ? 0.14 : 0.08)))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .strokeBorder(agent.color.opacity(paused ? 0.6 : 0), style: StrokeStyle(lineWidth: 1, dash: [3, 3])))
        .opacity(paused ? 0.55 : 1)
        .contentShape(RoundedRectangle(cornerRadius: 10))
        .onHover { hovered = $0 }
    }
}

/// Slight shrink on press, Dynamic Island style.
struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.94 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

/// needs_human option: fills with the agent color on hover/press.
struct OptionButtonStyle: ButtonStyle {
    let color: Color
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(Capsule().fill(color.opacity(configuration.isPressed ? 0.5 : (hovered ? 0.28 : 0))))
            .scaleEffect(configuration.isPressed ? 0.94 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.6), value: configuration.isPressed)
            .onHover { hovered = $0 }
    }
}

struct BudgetBar: View {
    let budget: Budget

    private var fraction: Double {
        budget.total > 0 ? min(budget.spent / budget.total, 1) : 0
    }

    var body: some View {
        HStack(spacing: 6) {
            Text("💰")
                .font(.system(size: 11))
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.15))
                Capsule()
                    .fill(fraction > 0.9 ? Color.orange : Color.green)
                    .frame(width: 90 * fraction)
            }
            .frame(width: 90, height: 6)
            Text(String(format: "$%.0f / $%.0f", budget.spent, budget.total))
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundColor(.white.opacity(0.85))
        }
    }
}
