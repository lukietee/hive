import AppKit
import SwiftUI

/// `Hive --thumbnail out.png`: the Devpost / social thumbnail, drawn with the app's own logo,
/// notch shape and ghost cursors. 1500x1000 (3:2) at 2x.
@MainActor
enum Thumbnail {
    static let size = CGSize(width: 1500, height: 1000)

    static func render(to url: URL) {
        let r = ImageRenderer(content: ThumbnailView().frame(width: size.width, height: size.height))
        r.scale = 2
        guard let cg = r.cgImage,
              let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) else {
            print("thumbnail: render failed")
            return
        }
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? png.write(to: url)
        print("thumbnail \(url.path)")
    }
}

private struct ThumbCursor: Identifiable {
    let id: String
    let at: CGPoint          // arrow tip
    let from: CGPoint        // where its dotted trail starts
    var ripple = false
}

struct ThumbnailView: View {
    private let cursors: [ThumbCursor] = [
        ThumbCursor(id: "fixer", at: CGPoint(x: 205, y: 690), from: CGPoint(x: 110, y: 540), ripple: true),
        ThumbCursor(id: "web", at: CGPoint(x: 1180, y: 300), from: CGPoint(x: 1330, y: 200)),
        ThumbCursor(id: "deck", at: CGPoint(x: 1225, y: 650), from: CGPoint(x: 1380, y: 760), ripple: true),
        ThumbCursor(id: "social", at: CGPoint(x: 1010, y: 845), from: CGPoint(x: 900, y: 940)),
        ThumbCursor(id: "cake", at: CGPoint(x: 330, y: 300), from: CGPoint(x: 180, y: 220)),
        ThumbCursor(id: "food", at: CGPoint(x: 470, y: 860), from: CGPoint(x: 330, y: 930), ripple: true),
        ThumbCursor(id: "treasurer", at: CGPoint(x: 720, y: 905), from: CGPoint(x: 650, y: 980)),
        ThumbCursor(id: "checker", at: CGPoint(x: 1040, y: 205), from: CGPoint(x: 940, y: 150)),
    ]

    var body: some View {
        ZStack(alignment: .topLeading) {
            background
            notch
            dottedGrid.opacity(0.35)
            ForEach(cursors) { c in trail(c) }
            hero
            ForEach(cursors) { c in cursor(c) }
        }
        .frame(width: Thumbnail.size.width, height: Thumbnail.size.height)
        .clipped()
        .environment(\.colorScheme, .dark)
    }

    // MARK: Layers

    private var background: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.06, green: 0.06, blue: 0.08), Color(red: 0.03, green: 0.03, blue: 0.04)],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [Color(red: 1, green: 0.72, blue: 0.1).opacity(0.22), .clear],
                           center: UnitPoint(x: 0.5, y: 0.5), startRadius: 0, endRadius: 520)
        }
    }

    /// The widget itself at the top, compact Live Activity style: agents on the left, status on the right.
    private var notch: some View {
        let w: CGFloat = 640, h: CGFloat = 64
        return ZStack {
            NotchShape(bottomRadius: 26, flare: 14).fill(Color.black)
                .overlay(NotchShape(bottomRadius: 26, flare: 14).stroke(Color.white.opacity(0.08), lineWidth: 1))
            HStack(spacing: 0) {
                HStack(spacing: -7) {
                    ForEach(["fixer", "web", "deck", "social", "cake"], id: \.self) { id in
                        let st = AgentPalette.style(for: id)
                        let rgb = RGB(hex: st.hex)
                        AgentBadge(color: rgb.color, onColor: rgb.onColor, symbol: st.symbol, size: 30)
                            .overlay(Circle().stroke(Color.black, lineWidth: 2.5))
                    }
                }
                Spacer()
                HStack(spacing: 8) {
                    HiveMark(size: 28)
                    Text("8 agents").font(.system(size: 20, weight: .semibold)).foregroundStyle(.white)
                }
            }
            .padding(.horizontal, 44)
            .padding(.bottom, 4)
        }
        .frame(width: w, height: h)
        .position(x: Thumbnail.size.width / 2, y: h / 2)
    }

    private var dottedGrid: some View {
        Canvas { ctx, size in
            for x in stride(from: 30.0, to: size.width, by: 40) {
                for y in stride(from: 110.0, to: size.height, by: 40) {
                    ctx.fill(Path(ellipseIn: CGRect(x: x, y: y, width: 2, height: 2)), with: .color(.white.opacity(0.18)))
                }
            }
        }
    }

    private var hero: some View {
        VStack(spacing: 18) {
            HStack(spacing: 26) {
                HiveMark(size: 150)
                    .shadow(color: Color(red: 1, green: 0.7, blue: 0.1).opacity(0.55), radius: 40)
                Text("Hive")
                    .font(.system(size: 150, weight: .bold))
                    .tracking(-3)
                    .foregroundStyle(.white)
            }
            Text("A swarm of AI agents that works your computer.")
                .font(.system(size: 34, weight: .medium))
                .foregroundStyle(Color.white.opacity(0.78))
            Text("Text it a task. Watch the team work.")
                .font(.system(size: 26, weight: .regular))
                .foregroundStyle(Color.white.opacity(0.5))
        }
        .frame(width: Thumbnail.size.width)
        .position(x: Thumbnail.size.width / 2, y: 520)
    }

    // MARK: Cursors

    private func trail(_ c: ThumbCursor) -> some View {
        let color = RGB(hex: AgentPalette.style(for: c.id).hex).color
        return Path { p in
            p.move(to: c.from)
            let mid = CGPoint(x: (c.from.x + c.at.x) / 2 + (c.at.y - c.from.y) * 0.25,
                              y: (c.from.y + c.at.y) / 2 - (c.at.x - c.from.x) * 0.25)
            p.addQuadCurve(to: c.at, control: mid)
        }
        .stroke(color.opacity(0.55), style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [2, 9]))
    }

    private func cursor(_ c: ThumbCursor) -> some View {
        let st = AgentPalette.style(for: c.id)
        let rgb = RGB(hex: st.hex)
        return ZStack(alignment: .topLeading) {
            if c.ripple {
                Circle().stroke(rgb.color.opacity(0.7), lineWidth: 3).frame(width: 56, height: 56).offset(x: -28, y: -28)
                Circle().stroke(rgb.color.opacity(0.3), lineWidth: 3).frame(width: 90, height: 90).offset(x: -45, y: -45)
            }
            ArrowShape()
                .fill(rgb.color)
                .overlay(ArrowShape().stroke(Color.white, style: StrokeStyle(lineWidth: 2.4, lineJoin: .round)))
                .frame(width: 30, height: 48)
                .shadow(color: .black.opacity(0.5), radius: 6, y: 3)
            HStack(spacing: 6) {
                Image(systemName: st.symbol).font(.system(size: 15, weight: .bold))
                Text(st.name).font(.system(size: 19, weight: .bold))
            }
            .foregroundStyle(rgb.onColor)
            .padding(.horizontal, 13)
            .padding(.vertical, 6)
            .background(Capsule().fill(rgb.color))
            .overlay(Capsule().stroke(Color.white.opacity(0.75), lineWidth: 1.5))
            .shadow(color: .black.opacity(0.35), radius: 6, y: 2)
            .offset(x: 26, y: 42)
            .fixedSize()
        }
        .offset(x: c.at.x, y: c.at.y)
    }
}
