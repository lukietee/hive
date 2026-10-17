import AppKit
import SwiftUI

/// `Hive --snapshot DIR`: renders the notch in each state to PNGs (no Screen Recording needed).
@MainActor
enum NotchSnapshots {
    static let notch = CGSize(width: 200, height: 32)

    static func render(to dir: URL) {
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let states: [(String, (HiveStore) -> Void)] = [
            ("1-idle", { _ in }),
            ("2-peek", { s in s.connected = true; s.hovering = true }),
            ("3-working", { s in populate(s); s.hovering = true; s.handle(ev("chat", "web", ["text": "🔵 Pricing section filled in"])) }),
            ("3b-compact", { s in populate(s) }),
            ("3c-compact-party", { s in
                for id in ["guests", "cake", "food", "treasurer", "caller"] { s.handle(ev("agent_spawn", id, [:])) }
                s.handle(ev("budget", "treasurer", ["spent": 62, "total": 150, "caps": [:]]))
            }),
            ("4-question", { s in
                populate(s)
                s.handle(ev("needs_human", "checker", ["question": "The site says $39 but the deck says $29. Which price is right?",
                                                        "options": ["$29", "$39"]]))
            }),
            ("5-paused", { s in populate(s); s.hovering = true; s.paused = ["social"] }),
            ("6b-summary-compact", { s in
                s.handle(ev("swarm_summary", "", ["title": "Pitch ready", "lines": []]))
            }),
            ("6-summary", { s in
                s.hovering = true
                s.handle(ev("swarm_summary", "", ["title": "Pitch ready with 1:50 to spare", "lines": [
                    "🔴 Fixer: 5/5 tests passing", "🔵 Web: hero, logo, pricing and waitlist fixed",
                    "🟡 Deck: 10/10 slides, market size $4B", "🟣 Social: launch post drafted (212 chars)",
                    "⚪ Checker: prices consistent at $29"]]))
            }),
            ("7-party", { s in
                for (id, st, p) in [("guests", "Texting 4 friends", 0.5), ("cake", "Calling Sweet Lady Jane", 0.3),
                                     ("food", "Comparing DoorDash carts", 0.6), ("treasurer", "Holding $150 budget", 0.4)] {
                    s.handle(ev("agent_spawn", id, [:]))
                    s.handle(ev("agent_status", id, ["text": st, "progress": p]))
                }
                s.handle(ev("budget", "treasurer", ["spent": 62, "total": 150, "caps": [:]]))
                s.hovering = true
            }),
        ]
        let size = NotchPanelController.panelSize
        for (name, setup) in states {
            let store = HiveStore()
            setup(store)
            let view = ZStack(alignment: .top) {
                LinearGradient(colors: [Color(red: 0.36, green: 0.42, blue: 0.62), Color(red: 0.62, green: 0.5, blue: 0.62)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                Rectangle().fill(Color.white.opacity(0.18)).frame(height: notch.height)  // menu bar
                NotchView(store: store, notchSize: notch)
            }
            .frame(width: size.width, height: size.height)
            .transaction { $0.animation = nil }
            let r = ImageRenderer(content: view)
            r.scale = 2
            guard let cg = r.cgImage else { print("snapshot \(name): render failed"); continue }
            let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])
            let url = dir.appendingPathComponent("\(name).png")
            try? png?.write(to: url)
            print("snapshot \(url.path)")
        }
    }

    private static func populate(_ s: HiveStore) {
        s.connected = true
        for (id, st, p) in [("fixer", "Running node --test", 0.7), ("web", "Filling in pricing", 0.45),
                             ("deck", "Slide 6 · market chart", 0.6), ("social", "Drafting launch post", 0.3),
                             ("checker", "Comparing prices", 0.2)] {
            s.handle(ev("agent_spawn", id, [:]))
            s.handle(ev("agent_status", id, ["text": st, "progress": p]))
        }
        s.handle(ev("countdown", "", ["seconds_left": 222]))
    }

    private static func ev(_ type: String, _ agent: String, _ data: [String: Any]) -> [String: Any] {
        ["type": type, "agent": agent, "data": data]
    }
}
