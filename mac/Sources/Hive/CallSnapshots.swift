import AppKit
import SwiftUI

/// Part of `Hive --snapshot DIR`: the Call window mid-call and after it ends.
@MainActor
enum CallSnapshots {
    static func render(to dir: URL) {
        let lines: [(String, String)] = [
            ("them", "Hi, Copper Whisk Bakery, this is Dana."),
            ("agent", "Hi Dana! This is Hive, an AI assistant calling on behalf of Lucas. Just so you know, I'm an AI "
                + "and this call is being recorded for a hackathon demo. Is now still a good time?"),
            ("them", "Oh, hi! Yes, I was expecting your call. Go ahead."),
            ("agent", "Great. Lucas said you might have a matcha cake in the case today?"),
            ("them", "We do. We have a six-inch matcha cake left. It's 38 dollars."),
        ]
        func ev(_ type: String, _ d: [String: Any]) -> (String, [String: Any]) {
            (type, d.merging(["call_id": "snap"]) { $1 })
        }
        var live: [(String, [String: Any])] = [
            ev("call_started", ["to": "+13105550142", "label": "Copper Whisk Bakery", "mode": "fake"]),
            ev("call_state", ["state": "connected"]),
        ]
        live += lines.map { ev("call_transcript", ["speaker": $0.0, "text": $0.1, "final": true]) }
        live.append(ev("call_transcript", ["speaker": "agent", "text": "Perfect, we'll take it. Could you write",
                                           "final": false]))
        let ended = live + [
            ev("call_transcript", ["speaker": "agent", "text": "Perfect, we'll take it. Could you write "
                                   + "\"Happy 21st Maya\" on top?", "final": true]),
            ev("call_ended", ["duration_s": 62, "outcome": "success",
                              "summary": "Confirmed with Dana at Copper Whisk Bakery: 6-inch matcha cake, "
                                  + "\"Happy 21st Maya\", ready at 6:00 PM, $38 at pickup.",
                              "details": ["pickup_time": "6:00 PM", "price": 38, "writing": "Happy 21st Maya"]]),
        ]
        for (name, events) in [("8-call-live", live), ("9-call-ended", ended)] {
            let model = CallModel()
            for (type, d) in events { model.handle(type, agent: "cake", d) }
            model.spokeAt = Date()
            model.speaker = "them"
            let size = CallWindowController.size
            let view = ZStack {
                LinearGradient(colors: [Color(red: 0.36, green: 0.42, blue: 0.62), Color(red: 0.62, green: 0.5, blue: 0.62)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                CallView(model: model)
            }
            .frame(width: size.width + 60, height: size.height + 60)
            .transaction { $0.animation = nil }
            let r = ImageRenderer(content: view)
            r.scale = 2
            guard let cg = r.cgImage else { print("snapshot \(name): render failed"); continue }
            let url = dir.appendingPathComponent("\(name).png")
            try? NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])?.write(to: url)
            print("snapshot \(url.path)")
        }
    }
}
