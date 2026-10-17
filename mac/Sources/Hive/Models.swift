import AppKit
import SwiftUI

// MARK: - Agent palette (mirrors docs/CONTRACT.md)

struct AgentStyle {
    let name: String
    let hex: String
    let emoji: String
}

enum AgentPalette {
    static let table: [String: AgentStyle] = [
        "builder": AgentStyle(name: "Builder", hex: "#34C759", emoji: "🟢"),
        "fixer": AgentStyle(name: "Fixer", hex: "#FF3B30", emoji: "🔴"),
        "web": AgentStyle(name: "Web", hex: "#0A84FF", emoji: "🔵"),
        "deck": AgentStyle(name: "Deck", hex: "#FFCC00", emoji: "🟡"),
        "social": AgentStyle(name: "Social", hex: "#AF52DE", emoji: "🟣"),
        "checker": AgentStyle(name: "Checker", hex: "#E5E5EA", emoji: "⚪"),
        "design": AgentStyle(name: "Design", hex: "#FF9F0A", emoji: "🎨"),
        "treasurer": AgentStyle(name: "Treasurer", hex: "#30D158", emoji: "💰"),
        "guests": AgentStyle(name: "Guests", hex: "#FF375F", emoji: "💌"),
        "cake": AgentStyle(name: "Cake", hex: "#FFD60A", emoji: "🎂"),
        "food": AgentStyle(name: "Food", hex: "#FF6B35", emoji: "🍕"),
    ]

    static func style(for id: String) -> AgentStyle {
        table[id] ?? AgentStyle(name: id.capitalized, hex: "#8E8E93", emoji: "•")
    }
}

// MARK: - Color helpers

struct RGB {
    var r: Double
    var g: Double
    var b: Double

    init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s.removeFirst() }
        var v: UInt64 = 0
        Scanner(string: s).scanHexInt64(&v)
        if s.count == 6 {
            r = Double((v >> 16) & 0xFF) / 255
            g = Double((v >> 8) & 0xFF) / 255
            b = Double(v & 0xFF) / 255
        } else {
            r = 0.56; g = 0.56; b = 0.58
        }
    }

    var color: Color { Color(red: r, green: g, blue: b) }
    var luminance: Double { 0.2126 * r + 0.7152 * g + 0.0722 * b }
    /// Readable text color on top of this color.
    var onColor: Color { luminance > 0.6 ? Color.black.opacity(0.85) : .white }
}

// MARK: - State

struct AgentState: Identifiable {
    let id: String
    var name: String
    var color: Color
    var onColor: Color
    var emoji: String
    /// Global screen point, top-left origin (contract coordinates).
    var position: CGPoint
    var status: String = ""
    var progress: Double? = nil
    var caption: String? = nil
    var typingText: String? = nil
    var needsHuman: Bool = false
    var scale: CGFloat = 1
    var opacity: Double = 1
    var leaving: Bool = false
}

enum HighlightStyle: String {
    case circle, box, select
}

struct Highlight: Identifiable {
    let id = UUID()
    var rect: CGRect          // global, top-left origin
    var style: HighlightStyle
    var color: Color
    var sticky: Bool
}

struct LinkLine: Identifiable {
    let id = UUID()
    var from: CGPoint
    var to: CGPoint
    var text: String?
    var color: Color
}

struct Ripple: Identifiable {
    let id = UUID()
    var point: CGPoint
    var color: Color
}

struct HumanQuestion {
    var agent: String
    var question: String
    var options: [String]
}

struct Budget {
    var spent: Double
    var total: Double
    var caps: [String: Double]
}

struct SummaryCard {
    var title: String
    var lines: [String]
}

struct ChatLine {
    var agent: String
    var text: String
}

enum NotchMode: Equatable {
    case idle, expanded, summary
}
