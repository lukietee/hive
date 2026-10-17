import AppKit
import SwiftUI

/// Single source of truth for everything the notch and overlay draw.
/// Fed by EngineClient (real engine) or Simulator (scripted demo).
@MainActor
final class HiveStore: ObservableObject {
    @Published var agents: [String: AgentState] = [:]
    @Published var order: [String] = []
    @Published var highlights: [Highlight] = []
    @Published var links: [LinkLine] = []
    @Published var ripples: [Ripple] = []
    @Published var countdown: Int? = nil
    @Published var budget: Budget? = nil
    @Published var summary: SummaryCard? = nil
    @Published var question: HumanQuestion? = nil
    @Published var lastChat: ChatLine? = nil
    @Published var connected = false
    /// Agents the human paused from the notch (pause/resume commands).
    @Published var paused: Set<String> = []
    @Published var allPaused = false
    /// Pointer is over the notch panel (Dynamic Island-style peek).
    @Published var hovering = false
    /// Where notch/menu commands go: the engine socket, or the simulator log.
    var onCommand: ((String, [String: Any]) -> Void)?
    let deck = DeckViewerModel()

    private var typingTokens: [String: Int] = [:]
    private var chatToken = 0

    var notchMode: NotchMode {
        // Collapses to a compact Live Activity unless hovered. A pending question always
        // expands, so the human can answer without hunting for the notch.
        if summary != nil { return hovering ? .summary : .compact }
        if question != nil { return .expanded }
        if !order.isEmpty || countdown != nil || budget != nil { return hovering ? .expanded : .compact }
        return hovering ? .peek : .idle
    }

    /// Mean progress of the visible agents (for the compact ring).
    var overallProgress: Double {
        let ps = visibleAgents.map { $0.progress ?? 0 }
        return ps.isEmpty ? 0 : ps.reduce(0, +) / Double(ps.count)
    }

    var visibleAgents: [AgentState] {
        order.compactMap { agents[$0] }.filter { !$0.leaving }
    }

    func reset() {
        withAnimation(.easeOut(duration: 0.25)) {
            agents = [:]
            order = []
            highlights = []
            links = []
            ripples = []
            countdown = nil
            budget = nil
            summary = nil
            question = nil
            lastChat = nil
            paused = []
            allPaused = false
        }
        deck.reset()
    }

    // MARK: - Event handling

    /// Handles one contract event envelope (already JSON-decoded).
    func handle(_ obj: [String: Any]) {
        guard let type = obj["type"] as? String else { return }
        let agentId = (obj["agent"] as? String) ?? ""
        let d = (obj["data"] as? [String: Any]) ?? [:]

        // Any regular activity from the agent that asked a question resolves it.
        if let q = question, q.agent == agentId,
           ["agent_status", "moving_to", "click", "typing", "agent_done"].contains(type) {
            withAnimation(.easeOut(duration: 0.2)) {
                question = nil
                agents[agentId]?.needsHuman = false
            }
        }

        switch type {
        case "agent_spawn": spawn(agentId, d)
        case "agent_status": status(agentId, d)
        case "moving_to": move(agentId, d)
        case "click": click(agentId, d)
        case "typing": typing(agentId, d)
        case "highlight": highlight(agentId, d)
        case "link": link(agentId, d)
        case "needs_human": needsHuman(agentId, d)
        case "chat": chat(agentId, d)
        case "agent_done": done(agentId, d)
        case "swarm_summary": swarmSummary(d)
        case "countdown":
            if let s = num(d["seconds_left"]) { countdown = max(0, Int(s)) }
        case "budget":
            var caps: [String: Double] = [:]
            if let c = d["caps"] as? [String: Any] {
                for (k, v) in c { if let n = num(v) { caps[k] = n } }
            }
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                budget = Budget(spent: num(d["spent"]) ?? 0, total: num(d["total"]) ?? 0, caps: caps)
            }
        case "deck_loaded", "deck_focus", "deck_slide_updated": deck.handle(type, d)
        default:
            break
        }
    }

    // MARK: - Handlers

    @discardableResult
    private func ensureAgent(_ id: String, _ d: [String: Any] = [:]) -> Bool {
        guard !id.isEmpty else { return false }
        if agents[id] != nil { return true }
        let style = AgentPalette.style(for: id)
        let rgb = RGB(hex: (d["color"] as? String) ?? style.hex)
        let agent = AgentState(
            id: id,
            name: (d["name"] as? String) ?? style.name,
            color: rgb.color,
            onColor: rgb.onColor,
            symbol: (d["symbol"] as? String) ?? style.symbol,
            position: ScreenGeometry.notchAnchor,
            scale: 0.3,
            opacity: 0
        )
        agents[id] = agent
        order.append(id)
        withAnimation(.spring(response: 0.45, dampingFraction: 0.7)) {
            agents[id]?.scale = 1
            agents[id]?.opacity = 1
        }
        return true
    }

    private func spawn(_ id: String, _ d: [String: Any]) {
        if summary != nil { withAnimation { summary = nil } }
        if agents[id]?.leaving == true {
            agents[id] = nil
            order.removeAll { $0 == id }
        }
        guard ensureAgent(id, d) else { return }
        if let x = num(d["x"]), let y = num(d["y"]) {
            let target = CGPoint(x: x, y: y)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.06) { [weak self] in
                withAnimation(.timingCurve(0.22, 1, 0.36, 1, duration: 0.8)) {
                    self?.agents[id]?.position = target
                }
            }
        }
    }

    private func status(_ id: String, _ d: [String: Any]) {
        guard ensureAgent(id) else { return }
        withAnimation(.easeOut(duration: 0.3)) {
            if let t = d["text"] as? String { agents[id]?.status = CleanText.strip(t) }
            if let p = num(d["progress"]) { agents[id]?.progress = min(max(p, 0), 1) }
        }
    }

    private func move(_ id: String, _ d: [String: Any]) {
        guard ensureAgent(id), let x = num(d["x"]), let y = num(d["y"]) else { return }
        let duration = (num(d["duration_ms"]) ?? 300) / 1000
        agents[id]?.caption = d["label"] as? String
        agents[id]?.needsHuman = false
        withAnimation(.timingCurve(0.22, 1, 0.36, 1, duration: max(duration, 0.05))) {
            agents[id]?.position = CGPoint(x: x, y: y)
        }
    }

    private func click(_ id: String, _ d: [String: Any]) {
        guard ensureAgent(id), let agent = agents[id] else { return }
        let point: CGPoint
        if let x = num(d["x"]), let y = num(d["y"]) { point = CGPoint(x: x, y: y) } else { point = agent.position }
        let ripple = Ripple(point: point, color: agent.color)
        ripples.append(ripple)
        withAnimation(.easeOut(duration: 0.08)) { agents[id]?.scale = 0.82 }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.09) { [weak self] in
            withAnimation(.spring(response: 0.25, dampingFraction: 0.5)) { self?.agents[id]?.scale = 1 }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
            self?.ripples.removeAll { $0.id == ripple.id }
        }
    }

    private func typing(_ id: String, _ d: [String: Any]) {
        guard ensureAgent(id) else { return }
        if let x = num(d["x"]), let y = num(d["y"]) {
            withAnimation(.timingCurve(0.22, 1, 0.36, 1, duration: 0.25)) {
                agents[id]?.position = CGPoint(x: x, y: y)
            }
        }
        let token = (typingTokens[id] ?? 0) + 1
        typingTokens[id] = token
        withAnimation(.easeOut(duration: 0.15)) { agents[id]?.typingText = (d["text"] as? String) ?? "…" }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) { [weak self] in
            guard let self, self.typingTokens[id] == token else { return }
            withAnimation(.easeOut(duration: 0.3)) { self.agents[id]?.typingText = nil }
        }
    }

    private func highlight(_ id: String, _ d: [String: Any]) {
        guard let x = num(d["x"]), let y = num(d["y"]) else { return }
        let style = HighlightStyle(rawValue: (d["style"] as? String) ?? "box") ?? .box
        var rect: CGRect
        if let w = num(d["w"]), let h = num(d["h"]) {
            rect = CGRect(x: x, y: y, width: w, height: h)
        } else {
            rect = CGRect(x: x - 28, y: y - 28, width: 56, height: 56) // centered default
        }
        rect = rect.standardized
        let color = agents[id]?.color ?? RGB(hex: AgentPalette.style(for: id).hex).color
        let sticky = (d["sticky"] as? Bool) ?? false
        let h = Highlight(rect: rect, style: style, color: color, sticky: sticky)
        withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) { highlights.append(h) }
        if !sticky {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
                withAnimation(.easeOut(duration: 0.4)) { self?.highlights.removeAll { $0.id == h.id } }
            }
        }
    }

    private func link(_ id: String, _ d: [String: Any]) {
        guard let from = point(d["from"]), let to = point(d["to"]) else { return }
        let color = agents[id]?.color ?? RGB(hex: AgentPalette.style(for: id).hex).color
        let line = LinkLine(from: from, to: to, text: d["text"] as? String, color: color)
        withAnimation(.easeOut(duration: 0.35)) { links.append(line) }
        if !((d["sticky"] as? Bool) ?? false) {
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
                withAnimation(.easeOut(duration: 0.4)) { self?.links.removeAll { $0.id == line.id } }
            }
        }
    }

    private func needsHuman(_ id: String, _ d: [String: Any]) {
        guard ensureAgent(id) else { return }
        let options = (d["options"] as? [Any])?.map { "\($0)" } ?? []
        withAnimation(.spring(response: 0.4, dampingFraction: 0.75)) {
            agents[id]?.needsHuman = true
            question = HumanQuestion(agent: id, question: CleanText.strip((d["question"] as? String) ?? "Need your input"),
                                     options: options.map(CleanText.strip))
        }
    }

    private func chat(_ id: String, _ d: [String: Any]) {
        guard let text = d["text"] as? String else { return }
        chatToken += 1
        let token = chatToken
        withAnimation(.easeOut(duration: 0.2)) { lastChat = ChatLine(agent: id, text: CleanText.strip(text)) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.5) { [weak self] in
            guard let self, self.chatToken == token else { return }
            withAnimation(.easeOut(duration: 0.3)) { self.lastChat = nil }
        }
    }

    private func done(_ id: String, _ d: [String: Any]) {
        guard agents[id] != nil else { return }
        if let s = d["summary"] as? String { agents[id]?.status = CleanText.strip(s) }
        agents[id]?.leaving = true
        agents[id]?.typingText = nil
        agents[id]?.caption = nil
        withAnimation(.easeIn(duration: 0.6)) {
            agents[id]?.position = ScreenGeometry.notchAnchor
            agents[id]?.scale = 0.25
            agents[id]?.opacity = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) { [weak self] in
            guard let self, self.agents[id]?.leaving == true else { return }
            withAnimation(.easeOut(duration: 0.2)) {
                self.agents[id] = nil
                self.order.removeAll { $0 == id }
            }
        }
    }

    private func swarmSummary(_ d: [String: Any]) {
        let lines = (d["lines"] as? [Any])?.map { CleanText.strip("\($0)") } ?? []
        withAnimation(.spring(response: 0.5, dampingFraction: 0.78)) {
            summary = SummaryCard(title: CleanText.strip((d["title"] as? String) ?? "Done"), lines: lines)
            question = nil
        }
    }

    // MARK: - Parsing helpers

    private func num(_ v: Any?) -> Double? {
        if let n = v as? NSNumber { return n.doubleValue }
        if let s = v as? String { return Double(s) }
        return nil
    }

    private func point(_ v: Any?) -> CGPoint? {
        if let a = v as? [Any], a.count >= 2, let x = num(a[0]), let y = num(a[1]) {
            return CGPoint(x: x, y: y)
        }
        if let o = v as? [String: Any], let x = num(o["x"]), let y = num(o["y"]) {
            return CGPoint(x: x, y: y)
        }
        return nil
    }
}
