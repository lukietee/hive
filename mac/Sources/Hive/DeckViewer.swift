import AppKit
import Combine
import SwiftUI

// MARK: - Controller

/// Owns the Deck Viewer window: shows it on deck_loaded, hides it on reset, and reports
/// where the slide sits on screen so the Deck agent's ghost cursor lands on the edited box.
///
/// Commands it sends to the engine (docs/CONTRACT.md):
///   deck_viewer {x, y, w, h}                   — the big slide's rect at 1× zoom (screen points)
///   deck_box    {slide, label, x, y, w, h}     — the focused box after zoom (screen points)
@MainActor
final class DeckViewerController {
    let model: DeckViewerModel
    private let store: HiveStore
    private let send: (String, [String: Any]) -> Void
    private var window: DeckViewerWindow?
    private var bag = Set<AnyCancellable>()

    init(store: HiveStore, send: @escaping (String, [String: Any]) -> Void) {
        self.store = store
        self.model = store.deck
        self.send = send

        model.onFocus = { [weak self] focus in self?.focused(focus) }
        model.onStageChanged = { [weak self] in self?.reportViewer() }

        model.$visible
            .removeDuplicates()
            .sink { [weak self] visible in
                // Published fires in willSet; act once the value is in place.
                DispatchQueue.main.async { visible ? self?.show() : self?.hide() }
            }
            .store(in: &bag)

        store.$connected
            .removeDuplicates()
            .filter { $0 }
            .sink { [weak self] _ in DispatchQueue.main.async { self?.reportViewer() } }
            .store(in: &bag)
    }

    // MARK: Window

    private func show() {
        if window == nil {
            let w = DeckViewerWindow(frame: Self.defaultFrame(), model: model, store: store)
            NotificationCenter.default.addObserver(
                forName: NSWindow.didMoveNotification, object: w, queue: .main
            ) { [weak self] _ in MainActor.assumeIsolated { self?.reportViewer() } }
            NotificationCenter.default.addObserver(
                forName: NSWindow.didResizeNotification, object: w, queue: .main
            ) { [weak self] _ in MainActor.assumeIsolated { self?.reportViewer() } }
            window = w
        }
        guard let window else { return }
        window.alphaValue = 0
        window.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.25
            window.animator().alphaValue = 1
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.reportViewer() }
    }

    private func hide() {
        guard let window, window.isVisible else { return }
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.2
            window.animator().alphaValue = 0
        }, completionHandler: {
            MainActor.assumeIsolated { window.orderOut(nil) }
        })
    }

    /// Bottom-left quadrant of the notch screen (overview §10, window ③), clear of the notch.
    static func defaultFrame() -> NSRect {
        let vf = ScreenGeometry.notchScreen.visibleFrame
        let w = min(860, max(520, vf.width * 0.48))
        let stageW = w - DeckLayout.stripWidth - DeckLayout.stagePadding * 2
        let h = stageW / (16.0 / 9.0) + DeckLayout.stagePadding * 2 + DeckLayout.headerHeight
        return NSRect(x: vf.minX + 16, y: vf.minY + 16, width: w, height: min(h, vf.height - 32))
    }

    // MARK: Geometry → engine

    /// The big slide's rect on screen (contract coordinates: global, top-left origin).
    var stageScreenRect: CGRect? {
        guard let window, window.isVisible, model.stageRectInWindow.width > 1 else { return nil }
        let s = model.stageRectInWindow
        let top = ScreenGeometry.primaryHeight - window.frame.maxY
        return CGRect(x: window.frame.minX + s.minX, y: top + s.minY, width: s.width, height: s.height)
    }

    /// A box (slide fractions) on screen, after the viewer's zoom for that box.
    func screenRect(forBox box: CGRect, zoom: CGFloat) -> CGRect? {
        guard let stage = stageScreenRect else { return nil }
        let anchor = DeckViewerModel.anchor(for: box, zoom: zoom)
        let z = DeckViewerModel.zoomedRect(box: box, zoom: zoom, anchor: anchor, in: stage.size)
        return z.offsetBy(dx: stage.minX, dy: stage.minY)
    }

    private func reportViewer() {
        guard store.connected, let r = stageScreenRect else { return }
        send("deck_viewer", ["x": r.minX.rounded2, "y": r.minY.rounded2, "w": r.width.rounded2, "h": r.height.rounded2])
    }

    private func focused(_ f: DeckViewerModel.Focus) {
        guard let r = screenRect(forBox: f.box, zoom: DeckViewerModel.zoom(for: f.box)) else {
            deckLog("focus slide \(f.slide): viewer not on screen yet (stage \(model.stageRectInWindow), visible \(window?.isVisible ?? false))")
            return
        }
        if Self.debugDir != nil {
            deckLog("focus slide \(f.slide) box \(f.box) → screen \(r) · stage \(stageScreenRect ?? .zero) · window \(window?.frame ?? .zero)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in self?.snapshot("focus-\(f.slide)") }
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { [weak self] in self?.snapshot("after-\(f.slide)") }
        }
        if store.connected {
            send("deck_box", ["slide": f.slide, "label": f.label,
                              "x": r.minX.rounded2, "y": r.minY.rounded2, "w": r.width.rounded2, "h": r.height.rounded2])
        } else {
            // --sim: no engine to drive the cursor, so drive it here with the same events.
            store.handle(["v": 1, "agent": "deck", "type": "moving_to",
                          "data": ["x": r.midX, "y": r.midY, "duration_ms": 450, "label": f.label]])
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                self?.store.handle(["v": 1, "agent": "deck", "type": "click", "data": ["x": r.midX, "y": r.midY]])
            }
        }
    }
}

extension DeckViewerController {
    /// HIVE_DECK_DEBUG=/some/dir → log geometry and save PNG snapshots of the viewer window.
    /// Uses the window's own backing store, so it works without Screen Recording permission.
    static let debugDir: URL? = ProcessInfo.processInfo.environment["HIVE_DECK_DEBUG"].map { URL(fileURLWithPath: $0) }

    func snapshot(_ name: String) {
        guard let dir = Self.debugDir, let view = window?.contentView,
              let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: rep)
        guard let png = rep.representation(using: .png, properties: [:]) else { return }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(name).png")
        try? png.write(to: url)
        deckLog("snapshot \(url.path)")
    }
}

private extension CGFloat {
    var rounded2: Double { (Double(self) * 100).rounded() / 100 }
}

// MARK: - Window

final class DeckViewerWindow: NSWindow {
    init(frame: NSRect, model: DeckViewerModel, store: HiveStore) {
        super.init(contentRect: frame, styleMask: [.borderless, .resizable], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        level = .floating
        isMovableByWindowBackground = true
        isReleasedWhenClosed = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        minSize = NSSize(width: 420, height: 260)
        let host = NSHostingView(rootView: DeckViewerView(model: model, store: store))
        host.sizingOptions = []
        host.frame = NSRect(origin: .zero, size: frame.size)
        host.autoresizingMask = [.width, .height]
        contentView = host
        setFrame(frame, display: true)
    }

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

// MARK: - Views

enum DeckLayout {
    static let headerHeight: CGFloat = 34
    static let stripWidth: CGFloat = 132
    static let stagePadding: CGFloat = 16
    static let corner: CGFloat = 14
    static let yellow = Color(red: 1, green: 0.8, blue: 0)
}

struct DeckViewerView: View {
    @ObservedObject var model: DeckViewerModel
    @ObservedObject var store: HiveStore

    var body: some View {
        VStack(spacing: 0) {
            header
            HStack(spacing: 0) {
                strip
                Rectangle().fill(Color.white.opacity(0.06)).frame(width: 1)
                stageArea
            }
        }
        .background(Color(white: 0.11))
        .clipShape(RoundedRectangle(cornerRadius: DeckLayout.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: DeckLayout.corner, style: .continuous)
                .strokeBorder(Color.white.opacity(0.09), lineWidth: 1)
        )
    }

    // Header: who's editing what.
    private var header: some View {
        HStack(spacing: 8) {
            Circle().fill(DeckLayout.yellow).frame(width: 9, height: 9)
                .shadow(color: DeckLayout.yellow.opacity(0.6), radius: 4)
            Text("Deck").font(.system(size: 12, weight: .semibold)).foregroundStyle(.white)
            Text("pitch.pptx").font(.system(size: 12, weight: .regular, design: .monospaced))
                .foregroundStyle(.white.opacity(0.45))
            Spacer(minLength: 8)
            if let status = store.agents["deck"]?.status, !status.isEmpty {
                Text(status).font(.system(size: 11, weight: .medium)).foregroundStyle(.white.opacity(0.7))
                    .lineLimit(1).transition(.opacity)
            }
            if let ms = model.lastRenderMs {
                Text("render \(ms) ms").font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5))
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(Color.white.opacity(0.08)))
            }
        }
        .padding(.horizontal, 14)
        .frame(height: DeckLayout.headerHeight)
        .background(Color(white: 0.14))
    }

    // Left: slide thumbnails, auto-scrolled to the slide being edited.
    private var strip: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 10) {
                    ForEach(model.slides) { slide in
                        DeckThumb(slide: slide, aspect: model.aspect,
                                  selected: slide.index == model.current,
                                  flashing: model.flashSlide == slide.index)
                            .id(slide.index)
                    }
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
            }
            .onChange(of: model.current) { _, new in
                withAnimation(.easeInOut(duration: 0.35)) { proxy.scrollTo(new, anchor: .center) }
            }
        }
        .frame(width: DeckLayout.stripWidth)
        .background(Color(white: 0.09))
    }

    // Right: the big slide.
    private var stageArea: some View {
        GeometryReader { g in
            let avail = CGSize(width: max(1, g.size.width - DeckLayout.stagePadding * 2),
                               height: max(1, g.size.height - DeckLayout.stagePadding * 2))
            let size = fit(aspect: model.aspect, in: avail)
            DeckStage(model: model, size: size)
                .frame(width: size.width, height: size.height)
                .background(
                    GeometryReader { s in
                        let frame = s.frame(in: .global)
                        Color.clear
                            .onAppear { model.stageRectInWindow = frame }
                            .onChange(of: frame) { _, new in model.stageRectInWindow = new }
                    }
                )
                .position(x: g.size.width / 2, y: g.size.height / 2)
        }
    }

    private func fit(aspect: CGFloat, in size: CGSize) -> CGSize {
        if size.width / size.height > aspect {
            return CGSize(width: size.height * aspect, height: size.height)
        }
        return CGSize(width: size.width, height: size.width / aspect)
    }
}

private struct DeckStage: View {
    @ObservedObject var model: DeckViewerModel
    let size: CGSize

    var body: some View {
        let slide = model.slides.indices.contains(model.current) ? model.slides[model.current] : nil
        ZStack(alignment: .topLeading) {
            ZStack {
                Color.white
                if let img = slide?.image {
                    Image(nsImage: img)
                        .resizable()
                        .interpolation(.high)
                        .id("\(model.current)-\(slide?.shownVersion ?? 0)")
                        .transition(.opacity)
                } else {
                    ProgressView().controlSize(.small)
                }
            }
            .frame(width: size.width, height: size.height)
            .scaleEffect(model.zoom, anchor: model.zoomAnchor)
            .frame(width: size.width, height: size.height)
            .clipped()

            if let f = model.focus, f.slide == model.current {
                let r = DeckViewerModel.zoomedRect(box: f.box, zoom: model.zoom, anchor: model.zoomAnchor, in: size)
                SelectionHandles(label: f.label)
                    .frame(width: max(r.width, 4), height: max(r.height, 4))
                    .position(x: r.midX, y: r.midY)
                    .transition(.opacity)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipShape(RoundedRectangle(cornerRadius: 3))
        .shadow(color: .black.opacity(0.45), radius: 14, y: 6)
    }
}

/// Keynote/Figma-style selection: thin yellow box, 8 handles, a label chip.
private struct SelectionHandles: View {
    let label: String

    var body: some View {
        GeometryReader { g in
            let w = g.size.width, h = g.size.height
            ZStack(alignment: .topLeading) {
                Rectangle()
                    .strokeBorder(DeckLayout.yellow, lineWidth: 1.5)
                ForEach(Array(handlePoints(w, h).enumerated()), id: \.offset) { _, p in
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(Color.white)
                        .overlay(RoundedRectangle(cornerRadius: 1.5).strokeBorder(DeckLayout.yellow, lineWidth: 1.5))
                        .frame(width: 8, height: 8)
                        .position(p)
                }
                if !label.isEmpty {
                    Text(label)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.black.opacity(0.85))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(RoundedRectangle(cornerRadius: 4).fill(DeckLayout.yellow))
                        .fixedSize()
                        .offset(x: -1, y: h > 40 ? -20 : h + 6)
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func handlePoints(_ w: CGFloat, _ h: CGFloat) -> [CGPoint] {
        [CGPoint(x: 0, y: 0), CGPoint(x: w / 2, y: 0), CGPoint(x: w, y: 0),
         CGPoint(x: 0, y: h / 2), CGPoint(x: w, y: h / 2),
         CGPoint(x: 0, y: h), CGPoint(x: w / 2, y: h), CGPoint(x: w, y: h)]
    }
}

private struct DeckThumb: View {
    let slide: DeckViewerModel.Slide
    let aspect: CGFloat
    let selected: Bool
    let flashing: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Text("\(slide.index + 1)")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(.white.opacity(selected ? 0.9 : 0.4))
                .frame(width: 14, alignment: .trailing)
            ZStack {
                Color.white
                if let img = slide.image {
                    Image(nsImage: img).resizable().interpolation(.medium)
                        .id(slide.shownVersion)
                        .transition(.opacity)
                }
                if flashing {
                    DeckLayout.yellow.opacity(0.28).transition(.opacity)
                }
            }
            .aspectRatio(aspect, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 3))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(selected ? DeckLayout.yellow : Color.white.opacity(0.12), lineWidth: selected ? 2 : 1)
                    .padding(-2)
            )
        }
    }
}
