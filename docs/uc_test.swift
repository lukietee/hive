// Universal Control test: can SYNTHETIC mouse events push the cursor onto the iPad?
//
// Setup:
//   1. iPad plugged into the Mac, Universal Control on
//      (System Settings > Displays > Advanced > "Allow your pointer and keyboard to move between any nearby Mac or iPad").
//   2. Check which side the iPad is on in System Settings > Displays (arrangement).
//   3. Give your terminal app Accessibility permission
//      (System Settings > Privacy & Security > Accessibility), or the events are silently dropped.
//
// Run:   swift uc_test.swift right      (or: left)
// Watch the iPad. Don't touch the mouse while it runs.

import CoreGraphics
import Foundation

let side = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "right"
let dir: Double = side == "left" ? -1 : 1

let screen = CGDisplayBounds(CGMainDisplayID())
func pos() -> CGPoint { CGEvent(source: nil)!.location }
func move(dx: Double, dy: Double) {
    let p = pos()
    let target = CGPoint(x: p.x + dx, y: p.y + dy)
    let e = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                    mouseCursorPosition: target, mouseButton: .left)!
    // Universal Control likely watches movement deltas against the edge, so set them explicitly.
    e.setIntegerValueField(.mouseEventDeltaX, value: Int64(dx))
    e.setIntegerValueField(.mouseEventDeltaY, value: Int64(dy))
    e.post(tap: .cghidEventTap)
}
func click() {
    let p = pos()
    for type in [CGEventType.leftMouseDown, .leftMouseUp] {
        CGEvent(mouseEventSource: nil, mouseType: type,
                mouseCursorPosition: p, mouseButton: .left)!.post(tap: .cghidEventTap)
        usleep(60_000)
    }
}

print("Start: \(pos())  screen: \(screen)")

// 1. Glide to the edge facing the iPad.
let startX = side == "left" ? screen.minX + 5 : screen.maxX - 5
CGWarpMouseCursorPosition(CGPoint(x: startX, y: screen.midY))
usleep(300_000)

// 2. Keep pushing past the edge, like a person shoving the mouse sideways.
print("Pushing \(side) past the edge for ~2s… watch the iPad.")
for _ in 0..<200 {
    move(dx: 12 * dir, dy: 0)
    usleep(10_000)
}

// 3. If we crossed over, these moves should drive the pointer on the iPad.
print("Wiggling for ~2s (should be visible on the iPad if it crossed)…")
for i in 0..<120 {
    move(dx: 4 * dir, dy: i % 40 < 20 ? 6 : -6)
    usleep(15_000)
}

print("Clicking once at the current pointer spot (watch for a tap on the iPad)…")
click()

print("End: \(pos())")
print("""

RESULT CHECK:
  • Pointer appeared on the iPad and wiggled → synthetic crossing WORKS. Universal Control is viable.
  • Pointer stuck at the Mac's edge         → it ignores synthetic input. Use WebDriverAgent + mirror window.
""")
