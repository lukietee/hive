import AppKit

/// Converts between contract coordinates (global, top-left origin of the primary
/// display, y down — same space as CGEvent / Accessibility) and AppKit coordinates
/// (global, bottom-left origin of the primary display, y up).
enum ScreenGeometry {
    /// Height of the primary display (the one whose AppKit frame origin is 0,0).
    static var primaryHeight: CGFloat {
        let primary = NSScreen.screens.first { $0.frame.origin == .zero } ?? NSScreen.screens.first
        return primary?.frame.height ?? 0
    }

    /// A screen's frame expressed in contract (top-left) coordinates.
    static func cgRect(of screen: NSScreen) -> CGRect {
        let f = screen.frame
        return CGRect(x: f.minX, y: primaryHeight - f.maxY, width: f.width, height: f.height)
    }

    /// Contract point -> AppKit point.
    static func appKitPoint(_ p: CGPoint) -> CGPoint {
        CGPoint(x: p.x, y: primaryHeight - p.y)
    }

    /// Contract rect (global, top-left origin) -> AppKit window frame (bottom-left origin).
    static func appKitFrame(_ r: CGRect) -> NSRect {
        NSRect(x: r.minX, y: primaryHeight - r.maxY, width: r.width, height: r.height)
    }

    /// The screen that has the notch (built-in display), or the main screen.
    static var notchScreen: NSScreen {
        NSScreen.screens.first { $0.safeAreaInsets.top > 0 }
            ?? NSScreen.main
            ?? NSScreen.screens[0]
    }

    /// Size of the hardware notch, or a menu-bar-height pill on notchless screens.
    static func notchSize(on screen: NSScreen) -> CGSize {
        if screen.safeAreaInsets.top > 0,
           let left = screen.auxiliaryTopLeftArea,
           let right = screen.auxiliaryTopRightArea {
            let w = screen.frame.width - left.width - right.width
            return CGSize(width: max(w, 120), height: screen.safeAreaInsets.top)
        }
        return CGSize(width: 190, height: max(NSStatusBar.system.thickness, 24))
    }

    /// Where cursors spawn from and fly back to: just under the notch, in contract coordinates.
    static var notchAnchor: CGPoint {
        let screen = notchScreen
        let r = cgRect(of: screen)
        let n = notchSize(on: screen)
        return CGPoint(x: r.midX, y: r.minY + n.height + 6)
    }
}
