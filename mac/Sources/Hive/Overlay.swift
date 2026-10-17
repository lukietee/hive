import AppKit
import SwiftUI

// MARK: - Window

/// One transparent, click-through window per display. Each draws the shared
/// store, offset by its display's origin, so cursors can cross between screens.
final class OverlayWindow: NSWindow {
    init(screen: NSScreen, store: HiveStore) {
        super.init(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .screenSaver
        ignoresMouseEvents = true
        isReleasedWhenClosed = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        let origin = ScreenGeometry.cgRect(of: screen).origin
        let host = NSHostingView(rootView: OverlayView(store: store, origin: origin))
        host.frame = NSRect(origin: .zero, size: screen.frame.size)
        contentView = host
        setFrame(screen.frame, display: true)
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

// MARK: - Root view

struct OverlayView: View {
    @ObservedObject var store: HiveStore
    /// This display's top-left corner in contract coordinates.
    let origin: CGPoint

    private func local(_ p: CGPoint) -> CGPoint {
        CGPoint(x: p.x - origin.x, y: p.y - origin.y)
    }

    private func local(_ r: CGRect) -> CGRect {
        CGRect(origin: local(r.origin), size: r.size)
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear

            ForEach(store.links) { line in
                LinkView(line: line, from: local(line.from), to: local(line.to))
                    .transition(.opacity)
            }

            ForEach(store.highlights) { h in
                HighlightView(highlight: h, rect: local(h.rect))
                    .transition(.scale(scale: 1.15).combined(with: .opacity))
            }

            ForEach(store.ripples) { r in
                RippleView(color: r.color)
                    .offset(x: local(r.point).x - 24, y: local(r.point).y - 24)
            }

            ForEach(store.order, id: \.self) { id in
                if let agent = store.agents[id] {
                    CursorView(agent: agent)
                        .offset(x: local(agent.position).x, y: local(agent.position).y)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

// MARK: - Cursor

struct ArrowShape: Shape {
    func path(in rect: CGRect) -> Path {
        // Classic pointer, defined in an 11.5 x 18.5 unit box, tip at (0,0).
        let pts: [CGPoint] = [
            CGPoint(x: 0, y: 0), CGPoint(x: 0, y: 16), CGPoint(x: 4, y: 12.2),
            CGPoint(x: 6.9, y: 18.5), CGPoint(x: 9.6, y: 17.4), CGPoint(x: 6.8, y: 11.4),
            CGPoint(x: 11.5, y: 11.4),
        ]
        let sx = rect.width / 11.5
        let sy = rect.height / 18.5
        var p = Path()
        p.move(to: CGPoint(x: rect.minX + pts[0].x * sx, y: rect.minY + pts[0].y * sy))
        for pt in pts.dropFirst() {
            p.addLine(to: CGPoint(x: rect.minX + pt.x * sx, y: rect.minY + pt.y * sy))
        }
        p.closeSubpath()
        return p
    }
}

struct CursorView: View {
    let agent: AgentState

    var body: some View {
        ZStack(alignment: .topLeading) {
            if agent.needsHuman {
                PulseRing(color: agent.color)
                    .offset(x: -26, y: -26)
            }

            ArrowShape()
                .fill(agent.color)
                .overlay(ArrowShape().stroke(Color.white, style: StrokeStyle(lineWidth: 1.6, lineJoin: .round)))
                .frame(width: 17, height: 27)
                .shadow(color: .black.opacity(0.35), radius: 3, x: 0, y: 1.5)

            nameTag
                .offset(x: 15, y: 24)

            if let text = agent.typingText {
                Text("⌨︎ \(text)")
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .lineLimit(1)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.96)))
                    .foregroundColor(.black)
                    .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                    .frame(maxWidth: 260, alignment: .leading)
                    .fixedSize()
                    .offset(x: 15, y: 48)
                    .transition(.opacity)
            }
        }
        .scaleEffect(agent.scale, anchor: .topLeading)
        .opacity(agent.opacity)
    }

    private var nameTag: some View {
        HStack(spacing: 4) {
            Text(agent.name)
                .font(.system(size: 11, weight: .bold, design: .rounded))
            if let caption = agent.caption, !caption.isEmpty {
                Text("· \(caption)")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .lineLimit(1)
            }
        }
        .foregroundColor(agent.onColor)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule().fill(agent.color))
        .overlay(Capsule().stroke(Color.white.opacity(0.7), lineWidth: 1))
        .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
        .fixedSize()
    }
}

struct PulseRing: View {
    let color: Color
    @State private var animate = false

    var body: some View {
        Circle()
            .stroke(color, lineWidth: 3)
            .frame(width: 52, height: 52)
            .scaleEffect(animate ? 1.6 : 0.6)
            .opacity(animate ? 0 : 0.95)
            .onAppear {
                withAnimation(.easeOut(duration: 1.1).repeatForever(autoreverses: false)) {
                    animate = true
                }
            }
    }
}

// MARK: - Effects

struct RippleView: View {
    let color: Color
    @State private var animate = false

    var body: some View {
        Circle()
            .stroke(color, lineWidth: 3)
            .frame(width: 48, height: 48)
            .scaleEffect(animate ? 1.5 : 0.2)
            .opacity(animate ? 0 : 1)
            .onAppear {
                withAnimation(.easeOut(duration: 0.55)) { animate = true }
            }
    }
}

struct HighlightView: View {
    let highlight: Highlight
    let rect: CGRect

    var body: some View {
        Group {
            switch highlight.style {
            case .circle:
                Ellipse()
                    .stroke(highlight.color, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .frame(width: rect.width + 18, height: rect.height + 18)
                    .offset(x: rect.minX - 9, y: rect.minY - 9)
            case .box:
                RoundedRectangle(cornerRadius: 8)
                    .stroke(highlight.color, lineWidth: 3)
                    .background(RoundedRectangle(cornerRadius: 8).fill(highlight.color.opacity(0.08)))
                    .frame(width: rect.width + 8, height: rect.height + 8)
                    .offset(x: rect.minX - 4, y: rect.minY - 4)
            case .select:
                SelectionBox(color: Color(red: 0.04, green: 0.52, blue: 1.0))
                    .frame(width: rect.width, height: rect.height)
                    .offset(x: rect.minX, y: rect.minY)
            }
        }
        .shadow(color: highlight.color.opacity(0.6), radius: 6)
    }
}

/// Figma/Keynote-style selection: thin box plus corner handles.
struct SelectionBox: View {
    let color: Color

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            ZStack(alignment: .topLeading) {
                Rectangle().stroke(color, lineWidth: 1.5)
                ForEach(0..<4, id: \.self) { i in
                    let x = (i % 2 == 0) ? 0 : w
                    let y = (i < 2) ? 0 : h
                    Rectangle()
                        .fill(Color.white)
                        .overlay(Rectangle().stroke(color, lineWidth: 1.5))
                        .frame(width: 8, height: 8)
                        .offset(x: x - 4, y: y - 4)
                }
            }
        }
    }
}

struct LinkView: View {
    let line: LinkLine
    let from: CGPoint
    let to: CGPoint

    var body: some View {
        ZStack(alignment: .topLeading) {
            Path { p in
                p.move(to: from)
                p.addLine(to: to)
            }
            .stroke(line.color, style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [9, 7]))
            .shadow(color: .black.opacity(0.3), radius: 2)

            Circle().fill(line.color).frame(width: 10, height: 10).offset(x: from.x - 5, y: from.y - 5)
            Circle().fill(line.color).frame(width: 10, height: 10).offset(x: to.x - 5, y: to.y - 5)

            if let text = line.text {
                Text(text)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(Color.black.opacity(0.85)))
                    .foregroundColor(.white)
                    .fixedSize()
                    .position(x: (from.x + to.x) / 2, y: (from.y + to.y) / 2)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}
