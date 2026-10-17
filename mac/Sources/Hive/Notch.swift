import AppKit
import SwiftUI

// MARK: - Panel

@MainActor
final class NotchPanelController {
    static let panelSize = CGSize(width: 600, height: 340)

    private(set) var panel: NSPanel
    private let store: HiveStore

    init(store: HiveStore) {
        self.store = store
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.isMovable = false
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        // Display-only for now: never block clicks on the menu bar underneath.
        panel.ignoresMouseEvents = true
        panel.level = NSWindow.Level(rawValue: NSWindow.Level.mainMenu.rawValue + 3)
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        layout()
    }

    /// (Re)positions the panel at the top-center of the notch screen.
    func layout() {
        let screen = ScreenGeometry.notchScreen
        let size = Self.panelSize
        let frame = NSRect(x: screen.frame.midX - size.width / 2,
                           y: screen.frame.maxY - size.height,
                           width: size.width, height: size.height)
        let notch = ScreenGeometry.notchSize(on: screen)
        let host = NSHostingView(rootView: NotchView(store: store, notchSize: notch))
        host.frame = NSRect(origin: .zero, size: size)
        panel.contentView = host
        panel.setFrame(frame, display: true)
    }

    func show() {
        panel.orderFrontRegardless()
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

    private var width: CGFloat {
        switch mode {
        case .idle: return notchSize.width + 36
        case .expanded, .summary: return 520
        }
    }

    private var height: CGFloat {
        switch mode {
        case .idle:
            return notchSize.height
        case .expanded:
            let rows = CGFloat((store.visibleAgents.count + 2) / 3)
            var h = notchSize.height + 44 + rows * 46
            if store.question != nil { h += 34 }
            if store.lastChat != nil { h += 22 }
            return min(h + 12, NotchPanelController.panelSize.height)
        case .summary:
            let lines = CGFloat(min(store.summary?.lines.count ?? 0, 6))
            return min(notchSize.height + 64 + lines * 20, NotchPanelController.panelSize.height)
        }
    }

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
            .frame(width: width, height: height)
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
        default:
            expandedContent
        }
    }

    // MARK: Expanded

    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            header

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(store.visibleAgents) { agent in
                    AgentPill(agent: agent)
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
                Text(opt)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(Capsule().stroke(color, lineWidth: 1.5))
                    .foregroundColor(color)
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

    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                Circle().stroke(Color.white.opacity(0.15), lineWidth: 3)
                Circle()
                    .trim(from: 0, to: agent.progress ?? 0)
                    .stroke(agent.color, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Circle().fill(agent.color).frame(width: 8, height: 8)
                    .opacity(agent.needsHuman ? 0.4 : 1)
            }
            .frame(width: 22, height: 22)

            VStack(alignment: .leading, spacing: 1) {
                Text(agent.name)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
                Text(agent.needsHuman ? "Waiting for you…" : (agent.status.isEmpty ? "Starting…" : agent.status))
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundColor(agent.needsHuman ? agent.color : .white.opacity(0.6))
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: 38)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(0.08)))
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
