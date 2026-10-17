import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let store = HiveStore()
    private var client: EngineClient!
    private var simulator: Simulator!
    private var notch: NotchPanelController!
    private var overlays: [OverlayWindow] = []
    private var statusItem: NSStatusItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        client = EngineClient(store: store)
        simulator = Simulator(store: store)

        buildOverlays()
        notch = NotchPanelController(store: store)
        notch.show()
        setupStatusItem()

        NotificationCenter.default.addObserver(
            self, selector: #selector(screensChanged),
            name: NSApplication.didChangeScreenParametersNotification, object: nil)

        let args = CommandLine.arguments
        if args.contains("--sim") {
            simulator.run()
        } else {
            client.connect()
            if args.contains("--sim-fallback") {
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
                    guard let self, !self.store.connected else { return }
                    self.client.disconnect()
                    self.simulator.run()
                }
            }
        }
    }

    // MARK: - Windows

    private func buildOverlays() {
        overlays.forEach { $0.orderOut(nil) }
        overlays = NSScreen.screens.map { OverlayWindow(screen: $0, store: store) }
        overlays.forEach { $0.orderFrontRegardless() }
    }

    @objc private func screensChanged() {
        buildOverlays()
        notch.layout()
        notch.show()
    }

    // MARK: - Menu bar

    private func setupStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "🐝"
        let menu = NSMenu()
        menu.addItem(makeItem("Run Simulation", #selector(runSimulation), key: "s"))
        menu.addItem(makeItem("Stop Simulation", #selector(stopSimulation), key: ""))
        menu.addItem(makeItem("Reconnect to Engine", #selector(reconnect), key: "r"))
        menu.addItem(.separator())
        menu.addItem(makeItem("Quit Hive", #selector(quit), key: "q"))
        item.menu = menu
        statusItem = item
    }

    private func makeItem(_ title: String, _ action: Selector, key: String) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        return mi
    }

    @objc private func runSimulation() {
        client.disconnect()
        simulator.run()
    }

    @objc private func stopSimulation() {
        simulator.stop()
        store.reset()
    }

    @objc private func reconnect() {
        simulator.stop()
        store.reset()
        client.connect()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.accessory)
    app.run()
}
