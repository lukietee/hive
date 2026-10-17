import AppKit

/// Scripted ~40s "Pitch in 5"-style demo so the UI can be seen without an engine.
/// Emits the exact same event envelopes the engine would (docs/CONTRACT.md).
@MainActor
final class Simulator {
    private let store: HiveStore
    private var task: Task<Void, Never>?

    init(store: HiveStore) {
        self.store = store
    }

    var isRunning: Bool { task != nil }

    func stop() {
        task?.cancel()
        task = nil
    }

    func run() {
        stop()
        store.reset()

        let r = ScreenGeometry.cgRect(of: ScreenGeometry.notchScreen)
        var steps: [(t: Double, agent: String, type: String, data: [String: Any])] = []

        func pt(_ fx: Double, _ fy: Double) -> [String: Any] {
            ["x": r.minX + fx * r.width, "y": r.minY + fy * r.height]
        }
        func pair(_ fx: Double, _ fy: Double) -> [Double] {
            [r.minX + fx * r.width, r.minY + fy * r.height]
        }
        func add(_ t: Double, _ agent: String, _ type: String, _ data: [String: Any] = [:]) {
            steps.append((t, agent, type, data))
        }
        func merge(_ a: [String: Any], _ b: [String: Any]) -> [String: Any] {
            a.merging(b) { $1 }
        }
        /// Moves an agent around a region of the screen (fractions), clicking as it goes.
        func wander(_ agent: String, from t0: Double, to t1: Double, every dt: Double,
                    x: ClosedRange<Double>, y: ClosedRange<Double>, labels: [String], seed: UInt64) {
            var s = seed
            func rnd() -> Double {
                s = s &* 6364136223846793005 &+ 1442695040888963407
                return Double((s >> 33) % 10_000) / 10_000
            }
            var t = t0
            var i = 0
            while t < t1 {
                let fx = x.lowerBound + rnd() * (x.upperBound - x.lowerBound)
                let fy = y.lowerBound + rnd() * (y.upperBound - y.lowerBound)
                var data = merge(pt(fx, fy), ["duration_ms": 420])
                if i % 2 == 0, !labels.isEmpty { data["label"] = labels[(i / 2) % labels.count] }
                add(t, agent, "moving_to", data)
                add(t + 0.5, agent, "click", pt(fx, fy))
                t += dt
                i += 1
            }
        }

        // Countdown: 5:00 → 0:00 compressed into ~40s.
        for i in 0...40 {
            add(Double(i), "", "countdown", ["seconds_left": max(0, 300 - Int(Double(i) * 7.5))])
        }

        // Spawn: cursors pour out of the notch into their windows.
        add(0.3, "builder", "agent_spawn", pt(0.24, 0.30))
        add(0.7, "web", "agent_spawn", pt(0.72, 0.26))
        add(1.1, "deck", "agent_spawn", pt(0.26, 0.72))
        add(1.5, "fixer", "agent_spawn", pt(0.74, 0.74))
        add(1.9, "checker", "agent_spawn", pt(0.50, 0.50))

        add(2.2, "builder", "agent_status", ["text": "Writing signup feature", "progress": 0.1])
        add(2.2, "web", "agent_status", ["text": "Fixing hero section", "progress": 0.1])
        add(2.2, "deck", "agent_status", ["text": "Filling slide 3", "progress": 0.1])
        add(2.2, "fixer", "agent_status", ["text": "Watching Sentry", "progress": 0.0])
        add(2.2, "checker", "agent_status", ["text": "Cross-checking facts", "progress": 0.0])

        // Steady work in each quadrant.
        wander("builder", from: 3, to: 11, every: 1.6, x: 0.08...0.44, y: 0.16...0.48,
               labels: ["editing signup.ts", "running tests"], seed: 1)
        wander("web", from: 3.4, to: 17, every: 1.5, x: 0.55...0.92, y: 0.16...0.48,
               labels: ["hero", "pricing", "waitlist form"], seed: 2)

        // Deck: the Deck Viewer opens and fills blank slides (cursor driven by the viewer in --sim).
        let body = SyntheticDeck.bodyBox
        let stat = SyntheticDeck.statBox
        func boxArr(_ b: CGRect) -> [Double] { [b.minX, b.minY, b.width, b.height].map { Double($0) } }
        add(1.3, "deck", "deck_loaded", ["slides": SyntheticDeck.content.count, "base": "sim://deck", "version": 1])
        var deckVersion = 1
        for (i, (t, slide, label)) in [(4.0, 0, "slide 1 · tagline"), (8.0, 1, "slide 2 · problem"),
                                       (12.0, 2, "slide 3 · solution"), (16.5, 3, "slide 4 · pricing")].enumerated() {
            add(t, "deck", "deck_focus", ["slide": slide, "box": boxArr(body), "label": label])
            add(t + 0.9, "deck", "typing", ["text": SyntheticDeck.content[slide].done])
            deckVersion += 1
            add(t + 1.6, "deck", "deck_slide_updated", ["slide": slide, "version": deckVersion, "render_ms": 560 + i * 17])
        }

        add(6.0, "web", "highlight", merge(pt(0.56, 0.17), ["w": r.width * 0.34, "h": r.height * 0.10, "style": "box"]))
        add(6.4, "web", "agent_status", ["text": "Hero fixed ✓ · pricing next", "progress": 0.35])
        add(8.0, "builder", "typing", merge(pt(0.20, 0.34), ["text": "func signup(user: User?) {"]))
        add(10.0, "builder", "agent_status", ["text": "Tests: 1 failing ✗", "progress": 0.5])
        add(10.0, "builder", "chat", ["text": "test 3 fails — null user on signup"])

        // Fixer: Sentry → patch in VS Code.
        add(10.5, "fixer", "agent_status", ["text": "Sentry: null user on signup", "progress": 0.3])
        add(10.6, "fixer", "moving_to", merge(pt(0.70, 0.66), ["duration_ms": 500, "label": "reading stack trace"]))
        add(11.2, "fixer", "highlight", merge(pt(0.62, 0.64), ["w": r.width * 0.18, "h": r.height * 0.04, "style": "circle"]))
        add(13.0, "fixer", "moving_to", merge(pt(0.28, 0.40), ["duration_ms": 900, "label": "patching line 42"]))
        add(14.0, "fixer", "click", pt(0.28, 0.40))
        add(14.2, "fixer", "typing", merge(pt(0.28, 0.40), ["text": "guard let user else { return .invalid }"]))
        add(15.5, "builder", "agent_status", ["text": "Tests green ✓", "progress": 0.85])
        add(15.6, "fixer", "agent_status", ["text": "Patched ✓", "progress": 1.0])
        add(15.6, "fixer", "chat", ["text": "Patched ✓ redeploying"])

        // Deck: selection handles while it fills slides.
        add(9.8, "deck", "agent_status", ["text": "Slide 2 done ✓", "progress": 0.35])
        add(18.4, "deck", "agent_status", ["text": "Slide 4 done ✓", "progress": 0.6])

        // Checker: price mismatch between the site and the deck.
        add(18.0, "checker", "moving_to", merge(pt(0.76, 0.32), ["duration_ms": 700, "label": "site pricing"]))
        add(18.8, "checker", "highlight", merge(pt(0.76, 0.32), ["style": "circle"]))
        add(19.6, "checker", "moving_to", merge(pt(0.30, 0.80), ["duration_ms": 800, "label": "deck pricing"]))
        add(20.4, "checker", "highlight", merge(pt(0.30, 0.80), ["style": "circle"]))
        add(20.6, "checker", "link", ["from": pair(0.76, 0.32), "to": pair(0.30, 0.80), "text": "price mismatch: $39 ≠ $29"])
        add(20.8, "checker", "chat", ["text": "Price mismatch between site and deck"])
        add(21.5, "web", "agent_status", ["text": "Pricing → $29", "progress": 0.8])

        // Deck asks the human.
        add(22.5, "deck", "needs_human", ["question": "Slide 5 market size?", "options": ["$2B", "$4B"]])
        add(27.0, "deck", "agent_status", ["text": "Using $4B ✓", "progress": 0.9])
        add(27.2, "deck", "deck_focus", ["slide": 4, "box": boxArr(stat), "label": "slide 5 · market size"])
        add(28.0, "deck", "typing", ["text": "$4B market"])
        add(28.6, "deck", "deck_slide_updated", ["slide": 4, "version": deckVersion + 1, "render_ms": 571])

        // Wrap up.
        add(29.0, "web", "agent_status", ["text": "Deployed ✓ pitchin5.xyz", "progress": 1.0])
        add(30.0, "deck", "agent_status", ["text": "All slides ✓", "progress": 1.0])
        add(30.5, "builder", "agent_status", ["text": "Feature shipped ✓", "progress": 1.0])
        add(31.0, "checker", "agent_status", ["text": "All consistent ✓", "progress": 1.0])

        add(33.0, "fixer", "agent_done")
        add(33.5, "builder", "agent_done")
        add(34.0, "web", "agent_done")
        add(34.5, "deck", "agent_done")
        add(35.0, "checker", "agent_done")
        add(36.5, "", "swarm_summary", [
            "title": "5 agents · 5 deliverables · 4m 48s",
            "lines": [
                "Signup feature shipped, tests green",
                "Landing page live at pitchin5.xyz",
                "Deck finished — 10 slides",
                "Bug caught via Sentry and patched",
                "1 conflict caught by Checker",
            ],
        ])

        let ordered = steps.sorted { $0.t < $1.t }
        task = Task { @MainActor [weak self] in
            let start = Date()
            for step in ordered {
                let wait = step.t - Date().timeIntervalSince(start)
                if wait > 0 { try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000)) }
                if Task.isCancelled { return }
                self?.store.handle([
                    "v": 1,
                    "ts": Date().timeIntervalSince1970,
                    "agent": step.agent,
                    "type": step.type,
                    "data": step.data,
                ])
            }
            self?.task = nil
        }
    }
}
