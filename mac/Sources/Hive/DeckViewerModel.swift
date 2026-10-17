import AppKit
import SwiftUI

/// State for the native Deck Viewer, fed by the deck_* contract events
/// (deck_loaded / deck_focus / deck_slide_updated, see docs/CONTRACT.md).
@MainActor
final class DeckViewerModel: ObservableObject {
    struct Slide: Identifiable {
        let index: Int
        var image: NSImage?
        /// Version of the image currently shown (crossfade key).
        var shownVersion: Int = 0
        /// Newest version requested from the engine.
        var wantedVersion: Int = 0
        var id: Int { index }
    }

    struct Focus: Equatable {
        var slide: Int
        /// Box in fractions of the slide (0–1), top-left origin.
        var box: CGRect
        var label: String
    }

    @Published var slides: [Slide] = []
    @Published var current = 0
    @Published var focus: Focus? = nil
    @Published var zoom: CGFloat = 1
    /// Zoom anchor (kept after zooming out so the unzoom doesn't jump).
    @Published var zoomAnchor: UnitPoint = .center
    @Published var visible = false
    /// Slide that just got a new render (brief flash on its thumbnail).
    @Published var flashSlide: Int? = nil
    @Published var lastRenderMs: Int? = nil

    /// The big slide's rect in the window's content view (top-left origin). Set by the view.
    var stageRectInWindow: CGRect = .zero {
        didSet { if stageRectInWindow != oldValue { onStageChanged?() } }
    }

    /// Called after a deck_focus with the slide, box (fractions) and label; the controller
    /// turns it into screen points for the ghost cursor.
    var onFocus: ((Focus) -> Void)?
    var onStageChanged: (() -> Void)?

    private(set) var base = ""
    private var unzoomToken = 0
    private var flashToken = 0
    /// Synthetic (--sim) slides that have been "edited" so far.
    private var syntheticFilled: Set<Int> = []

    var isSynthetic: Bool { base.hasPrefix("sim:") }

    /// Slide aspect ratio (width / height); 16:9 until an image arrives.
    var aspect: CGFloat {
        if let img = slides.first(where: { $0.image != nil })?.image, img.size.height > 0 {
            return img.size.width / img.size.height
        }
        return 16.0 / 9.0
    }

    func reset() {
        withAnimation(.easeOut(duration: 0.2)) {
            slides = []
            current = 0
            focus = nil
            zoom = 1
            visible = false
            flashSlide = nil
            lastRenderMs = nil
        }
        base = ""
    }

    // MARK: - Events

    func handle(_ type: String, _ d: [String: Any]) {
        switch type {
        case "deck_loaded": loaded(d)
        case "deck_focus": focused(d)
        case "deck_slide_updated": updated(d)
        default: break
        }
    }

    private func loaded(_ d: [String: Any]) {
        let n = max(0, Int(num(d["slides"]) ?? 0))
        let version = Int(num(d["version"]) ?? 1)
        base = ((d["base"] as? String) ?? "").replacingOccurrences(of: "/+$", with: "", options: .regularExpression)
        syntheticFilled = []
        slides = (0..<n).map { Slide(index: $0, wantedVersion: version) }
        current = 0
        focus = nil
        zoom = 1
        withAnimation(.spring(response: 0.45, dampingFraction: 0.85)) { visible = true }
        for i in 0..<n { fetch(i, version: version) }
    }

    private func focused(_ d: [String: Any]) {
        guard let slide = num(d["slide"]).map({ Int($0) }), slides.indices.contains(slide) else { return }
        var box = CGRect(x: 0, y: 0, width: 1, height: 1)
        if let a = d["box"] as? [Any], a.count >= 4,
           let x = num(a[0]), let y = num(a[1]), let w = num(a[2]), let h = num(a[3]) {
            box = CGRect(x: x, y: y, width: w, height: h).standardized
        }
        let f = Focus(slide: slide, box: box, label: (d["label"] as? String) ?? "")
        unzoomToken += 1
        withAnimation(.timingCurve(0.22, 1, 0.36, 1, duration: 0.35)) {
            current = slide
            focus = f
            zoomAnchor = UnitPoint(x: box.midX, y: box.midY)
            zoom = Self.zoom(for: box)
        }
        onFocus?(f)
    }

    private func updated(_ d: [String: Any]) {
        guard let slide = num(d["slide"]).map({ Int($0) }), slides.indices.contains(slide) else { return }
        let version = Int(num(d["version"]) ?? Double(slides[slide].wantedVersion + 1))
        lastRenderMs = num(d["render_ms"]).map { Int($0) }
        slides[slide].wantedVersion = max(slides[slide].wantedVersion, version)
        if isSynthetic { syntheticFilled.insert(slide) }
        fetch(slide, version: version)

        // Zoom back out and drop the handles shortly after the edit lands.
        unzoomToken += 1
        let token = unzoomToken
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) { [weak self] in
            guard let self, self.unzoomToken == token else { return }
            withAnimation(.timingCurve(0.4, 0, 0.2, 1, duration: 0.45)) {
                self.zoom = 1
                self.focus = nil
            }
        }
    }

    // MARK: - Geometry

    /// Zoom factor that makes a small box readable; full-width boxes stay at 1×.
    static func zoom(for box: CGRect) -> CGFloat {
        let biggest = max(box.width, box.height, 0.01)
        return min(1.6, max(1.0, 0.62 / biggest))
    }

    /// Where `box` (slide fractions) ends up inside a stage of `size` once zoomed by `zoom`
    /// around the box's center, clipped to the stage. Same math the view uses.
    static func zoomedRect(box: CGRect, zoom: CGFloat, in size: CGSize) -> CGRect {
        let center = CGPoint(x: box.midX * size.width, y: box.midY * size.height)
        let w = box.width * size.width * zoom
        let h = box.height * size.height * zoom
        let r = CGRect(x: center.x - w / 2, y: center.y - h / 2, width: w, height: h)
        return r.intersection(CGRect(origin: .zero, size: size))
    }

    // MARK: - Images

    private func fetch(_ i: Int, version: Int) {
        if isSynthetic {
            apply(SyntheticDeck.image(slide: i, filled: syntheticFilled.contains(i)), to: i, version: version)
            return
        }
        guard let url = URL(string: "\(base)/slide-\(i).png?v=\(version)") else { return }
        Task { [weak self] in
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                deckLog("GET \(url.absoluteString) -> \(code) (\(data.count) bytes)")
                guard code == 200, let image = NSImage(data: data) else { return }
                self?.apply(image, to: i, version: version)
            } catch {
                deckLog("GET \(url.absoluteString) failed: \(error.localizedDescription)")
            }
        }
    }

    private func apply(_ image: NSImage, to i: Int, version: Int) {
        guard slides.indices.contains(i), version >= slides[i].shownVersion else { return }
        let isUpdate = slides[i].image != nil
        withAnimation(.easeInOut(duration: 0.45)) {
            slides[i].image = image
            slides[i].shownVersion = version
        }
        if isUpdate {
            flashToken += 1
            let token = flashToken
            withAnimation(.easeOut(duration: 0.15)) { flashSlide = i }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { [weak self] in
                guard let self, self.flashToken == token else { return }
                withAnimation(.easeOut(duration: 0.4)) { self.flashSlide = nil }
            }
        }
    }

    private func num(_ v: Any?) -> Double? {
        if let n = v as? NSNumber { return n.doubleValue }
        if let s = v as? String { return Double(s) }
        return nil
    }
}

/// Unbuffered log line (stderr), so it shows up even when stdout is redirected.
func deckLog(_ s: String) {
    FileHandle.standardError.write(Data("[deck] \(s)\n".utf8))
}

// MARK: - Synthetic slides for --sim

/// Draws stand-in slide images so the Deck Viewer can be previewed without the engine.
enum SyntheticDeck {
    static let content: [(title: String, todo: String, done: String)] = [
        ("Whisk", "TODO: tagline", "Matcha, delivered to your dorm"),
        ("Problem", "TODO: problem", "Good matcha is $7 a cup and 20 minutes away"),
        ("Solution", "TODO: solution", "Weekly ceremonial-grade tins + a whisk, at your door"),
        ("Pricing", "TODO: pricing", "$29/mo · $19 for students"),
        ("Market", "TODO: market size", "$4B US matcha market, growing 9% a year"),
    ]

    /// Box (slide fractions) the body text sits in — what deck_focus points at in the sim.
    static let bodyBox = CGRect(x: 0.06, y: 0.36, width: 0.88, height: 0.40)
    static let statBox = CGRect(x: 0.06, y: 0.36, width: 0.42, height: 0.26)

    static func image(slide: Int, filled: Bool) -> NSImage {
        let size = NSSize(width: 1280, height: 720)
        let img = NSImage(size: size)
        img.lockFocus()
        defer { img.unlockFocus() }
        // Background + accent bar.
        NSColor.white.setFill()
        NSRect(origin: .zero, size: size).fill()
        NSColor(calibratedRed: 0.36, green: 0.55, blue: 0.27, alpha: 1).setFill()
        NSRect(x: 0, y: size.height - 18, width: size.width, height: 18).fill()

        let c = content[slide % content.count]
        let title: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 64, weight: .bold),
            .foregroundColor: NSColor(calibratedWhite: 0.1, alpha: 1),
        ]
        (c.title as NSString).draw(at: NSPoint(x: 77, y: size.height - 170), withAttributes: title)

        let body: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: filled ? 40 : 34, weight: filled ? .semibold : .regular),
            .foregroundColor: filled ? NSColor(calibratedWhite: 0.15, alpha: 1) : NSColor(calibratedWhite: 0.6, alpha: 1),
        ]
        let box = NSRect(x: bodyBox.minX * size.width, y: (1 - bodyBox.maxY) * size.height,
                         width: bodyBox.width * size.width, height: bodyBox.height * size.height)
        if !filled {
            NSColor(calibratedWhite: 0.85, alpha: 1).setStroke()
            let dash = NSBezierPath(rect: box.insetBy(dx: 2, dy: 2))
            dash.setLineDash([10, 8], count: 2, phase: 0)
            dash.lineWidth = 2
            dash.stroke()
        }
        ((filled ? c.done : c.todo) as NSString).draw(in: box.insetBy(dx: 24, dy: 24), withAttributes: body)

        let footer: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 20, weight: .medium),
            .foregroundColor: NSColor(calibratedWhite: 0.55, alpha: 1),
        ]
        ("\(slide + 1)" as NSString).draw(at: NSPoint(x: size.width - 70, y: 30), withAttributes: footer)
        return img
    }
}
