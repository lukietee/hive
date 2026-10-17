import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let store = HiveStore()
    private var client: EngineClient!
    private var simulator: Simulator!
    private var notch: NotchPanelController!
    private var overlays: [OverlayWindow] = []
    private var statusItem: NSStatusItem?
    private var pauseItem: NSMenuItem?
    /// True while the UI is driven by the built-in Simulator instead of the engine.
    private var simMode = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        // HIVE_ENGINE_URL overrides ws://127.0.0.1:8765 (tests, a teammate's engine).
        let url = ProcessInfo.processInfo.environment["HIVE_ENGINE_URL"].flatMap(URL.init(string:))
        client = EngineClient(store: store, url: url ?? EngineClient.defaultURL)
        simulator = Simulator(store: store)
        store.onCommand = { [weak self] cmd, args in self?.route(cmd, args) }

        buildOverlays()
        notch = NotchPanelController(store: store)
        notch.show()
        setupStatusItem()

        NotificationCenter.default.addObserver(
            self, selector: #selector(screensChanged),
            name: NSApplication.didChangeScreenParametersNotification, object: nil)

        let args = CommandLine.arguments
        if args.contains("--sim") {
            simMode = true
            simulator.run()
        } else {
            client.connect()
            if args.contains("--sim-fallback") {
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
                    guard let self, !self.store.connected else { return }
                    self.client.disconnect()
                    self.simMode = true
                    self.simulator.run()
                }
            }
            if args.contains("--selftest-commands") {
                runCommandSelfTest()
            }
        }
    }

    // MARK: - Commands

    /// Sends a notch/menu command to the engine, or handles it locally in sim mode.
    private func route(_ cmd: String, _ args: [String: Any]) {
        if simMode {
            log("[sim] \(cmd) \(args)")
            if cmd == "start" { simulator.run() }
            return
        }
        guard store.connected else {
            log("engine offline, dropped \(cmd) \(args); reconnecting")
            client.connect()
            return
        }
        client.send(cmd: cmd, args: args)
        log("→ engine \(cmd) \(args)")
    }

    private func log(_ s: String) {
        FileHandle.standardError.write(Data("[hive] \(s)\n".utf8))
    }

    /// `--selftest-commands`: once connected, fire every command through the same store
    /// actions the notch buttons use, then quit. Pair with a WS echo server to check the JSON.
    private func runCommandSelfTest() {
        Task { @MainActor [weak self] in
            guard let self else { return }
            for _ in 0..<50 where !self.store.connected {
                try? await Task.sleep(for: .milliseconds(100))
            }
            guard self.store.connected else { self.log("selftest: never connected"); NSApp.terminate(nil); return }
            let s = self.store
            s.start("pitch_in_5")
            s.start("demo_sim")
            s.handle(["type": "agent_spawn", "agent": "checker", "data": [:]])
            s.handle(["type": "agent_spawn", "agent": "web", "data": [:]])
            s.togglePause("web")       // pause {agent: web}
            s.togglePause("web")       // resume {agent: web}
            s.togglePauseAll()         // pause {}
            s.togglePauseAll()         // resume {}
            s.handle(["type": "needs_human", "agent": "checker",
                      "data": ["question": "Site says $39, deck says $29. Which?", "options": ["$29", "$39"]]])
            s.answer("$29")            // answer {agent: checker, choice: $29}
            self.log("selftest: question cleared = \(s.question == nil)")
            try? await Task.sleep(for: .milliseconds(500))
            NSApp.terminate(nil)
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
        menu.delegate = self
        menu.addItem(makeItem("Start Pitch in 5", #selector(startPitch), key: "p"))
        menu.addItem(makeItem("Start demo_sim", #selector(startDemoSim), key: "d"))
        let pause = makeItem("Pause All Agents", #selector(togglePauseAll), key: "")
        menu.addItem(pause)
        pauseItem = pause
        menu.addItem(.separator())
        menu.addItem(makeItem("Run Simulation (no engine)", #selector(runSimulation), key: "s"))
        menu.addItem(makeItem("Stop Simulation", #selector(stopSimulation), key: ""))
        menu.addItem(makeItem("Reconnect to Engine", #selector(reconnect), key: "r"))
        menu.addItem(.separator())
        menu.addItem(makeItem("Quit Hive", #selector(quit), key: "q"))
        item.menu = menu
        statusItem = item
    }

    func menuWillOpen(_ menu: NSMenu) {
        pauseItem?.title = store.anyPaused ? "Resume All Agents" : "Pause All Agents"
    }

    private func makeItem(_ title: String, _ action: Selector, key: String) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        return mi
    }

    @objc private func startPitch() { store.start("pitch_in_5") }
    @objc private func startDemoSim() { store.start("demo_sim") }
    @objc private func togglePauseAll() { store.togglePauseAll() }

    @objc private func runSimulation() {
        client.disconnect()
        simMode = true
        simulator.run()
    }

    @objc private func stopSimulation() {
        simulator.stop()
        store.reset()
    }

    @objc private func reconnect() {
        simulator.stop()
        simMode = false
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
