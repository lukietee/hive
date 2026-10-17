import SwiftUI

/// Human → engine commands triggered from the notch and the menu bar menu (docs/CONTRACT.md, "Commands").
extension HiveStore {
    func send(_ cmd: String, _ args: [String: Any] = [:]) {
        onCommand?(cmd, args)
    }

    func start(_ scenario: String) {
        send("start", ["scenario": scenario])
    }

    func isPaused(_ id: String) -> Bool {
        allPaused || paused.contains(id)
    }

    /// Click on an agent pill: pause or resume just that agent.
    func togglePause(_ id: String) {
        withAnimation(.easeOut(duration: 0.2)) {
            if isPaused(id) {
                if allPaused {
                    // Resuming one agent out of a global pause keeps the others paused.
                    allPaused = false
                    paused = Set(order)
                }
                paused.remove(id)
                send("resume", ["agent": id])
            } else {
                paused.insert(id)
                send("pause", ["agent": id])
            }
        }
    }

    var anyPaused: Bool { allPaused || !paused.isEmpty }

    func togglePauseAll() {
        withAnimation(.easeOut(duration: 0.2)) {
            if anyPaused {
                allPaused = false
                paused = []
                send("resume")
            } else {
                allPaused = true
                send("pause")
            }
        }
    }

    /// Reply to the open needs_human question, then collapse the question row.
    func answer(_ choice: String) {
        guard let q = question else { return }
        send("answer", ["agent": q.agent, "choice": choice])
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            question = nil
            agents[q.agent]?.needsHuman = false
        }
    }

    func dismissSummary() {
        withAnimation(.spring(response: 0.45, dampingFraction: 0.8)) { summary = nil }
    }
}
