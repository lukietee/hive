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
    /// `freeText` marks an answer the human typed via "Other…" instead of picking an option.
    func answer(_ choice: String, freeText: Bool = false) {
        guard let q = question else { return }
        var args: [String: Any] = ["agent": q.agent, "choice": choice]
        if freeText { args["free_text"] = true }
        send("answer", args)
        if editing == .other { endEditing() }
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            question = nil
            agents[q.agent]?.needsHuman = false
        }
    }

    /// Start a run from a typed goal (the engine's dynamic orchestrator).
    func startGoal(_ goal: String) {
        let text = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        send("start", ["scenario": "goal", "goal": text])
    }

    // MARK: Text fields

    func beginEditing(_ target: NotchEditing) {
        if target == .other && question == nil { return }
        draft = ""
        withAnimation(HiveStyle.spring) { editing = target }
    }

    func endEditing() {
        guard editing != nil else { return }
        withAnimation(HiveStyle.spring) { editing = nil }
        draft = ""
    }

    /// Return in the focused field.
    func submitDraft() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        switch editing {
        case .goal:
            guard !text.isEmpty else { return }
            startGoal(text)
            endEditing()
        case .other:
            guard !text.isEmpty else { return }
            answer(text, freeText: true)
        case nil:
            break
        }
    }

    func dismissSummary() {
        withAnimation(.spring(response: 0.45, dampingFraction: 0.8)) { summary = nil }
    }
}
