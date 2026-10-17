import AppKit
import SwiftUI

// MARK: - Agent palette (mirrors docs/CONTRACT.md)

struct AgentStyle {
    let name: String
    let hex: String
    /// SF Symbol shown in the agent's badge.
    let symbol: String
}

enum AgentPalette {
    static let table: [String: AgentStyle] = [
        "builder": AgentStyle(name: "Builder", hex: "#34C759", symbol: "hammer.fill"),
        "fixer": AgentStyle(name: "Fixer", hex: "#FF3B30", symbol: "wrench.and.screwdriver.fill"),
        "web": AgentStyle(name: "Web", hex: "#0A84FF", symbol: "globe"),
        "deck": AgentStyle(name: "Deck", hex: "#FFCC00", symbol: "rectangle.on.rectangle.angled.fill"),
        "social": AgentStyle(name: "Social", hex: "#AF52DE", symbol: "megaphone.fill"),
        "checker": AgentStyle(name: "Checker", hex: "#E5E5EA", symbol: "checkmark.shield.fill"),
        "design": AgentStyle(name: "Design", hex: "#FF9F0A", symbol: "paintbrush.pointed.fill"),
        "treasurer": AgentStyle(name: "Treasurer", hex: "#30D158", symbol: "creditcard.fill"),
        "guests": AgentStyle(name: "Guests", hex: "#FF375F", symbol: "envelope.fill"),
        "cake": AgentStyle(name: "Cake", hex: "#FFD60A", symbol: "birthday.cake.fill"),
        "food": AgentStyle(name: "Food", hex: "#FF6B35", symbol: "takeoutbag.and.cup.and.straw.fill"),
        "caller": AgentStyle(name: "Caller", hex: "#64D2FF", symbol: "phone.fill"),
        "conductor": AgentStyle(name: "Hive", hex: "#FFD60A", symbol: "hexagon.fill"),
    ]

    static func style(for id: String) -> AgentStyle {
        table[id] ?? AgentStyle(name: id.capitalized, hex: "#8E8E93", symbol: "sparkle")
    }

    /// Finds an agent by display name at the start of a line like "Fixer: 5/5 tests passing".
    static func match(line: String) -> (id: String, style: AgentStyle, rest: String)? {
        guard let colon = line.firstIndex(of: ":") else { return nil }
        let name = line[..<colon].trimmingCharacters(in: .whitespaces).lowercased()
        guard let (id, style) = table.first(where: { $0.value.name.lowercased() == name }) else { return nil }
        let rest = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        return (id, style, rest)
    }
}

// MARK: - Text cleanup

enum CleanText {
    /// Engine text sometimes leads with emoji ("🔴 Fixer: …", "🐝 Conductor: …").
    /// The UI uses SF Symbols instead, so drop emoji and tidy the spacing.
    static func strip(_ s: String) -> String {
        let kept = s.filter { ch in
            let scalars = ch.unicodeScalars
            let isEmoji = scalars.contains { $0.properties.isEmojiPresentation }
                || (scalars.contains { $0.value == 0xFE0F } && !ch.isASCII)
                || scalars.contains { $0.properties.isEmoji && $0.value >= 0x2190 && !$0.isASCII }
            return !isEmoji
        }
        return kept.split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
            .trimmingCharacters(in: .whitespaces)
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
    var symbol: String
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
    /// peek = idle + hovered: shows the Start controls.
    case idle, peek, expanded, summary
}
