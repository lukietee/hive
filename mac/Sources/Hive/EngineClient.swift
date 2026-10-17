import Foundation

/// WebSocket client for the Hive engine (ws://127.0.0.1:8765, see docs/CONTRACT.md).
/// Auto-reconnects every 2s and feeds decoded events into the store.
@MainActor
final class EngineClient {
    nonisolated static let defaultURL = URL(string: "ws://127.0.0.1:8765")!

    let url: URL
    private weak var store: HiveStore?
    private let session = URLSession(configuration: .default)
    private var task: URLSessionWebSocketTask?
    private var reconnectPending = false
    private var stopped = true

    init(store: HiveStore, url: URL = EngineClient.defaultURL) {
        self.store = store
        self.url = url
    }

    func connect() {
        stopped = false
        reconnectPending = false
        task?.cancel(with: .goingAway, reason: nil)
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        receive(on: t)
        t.sendPing { [weak self] error in
            Task { @MainActor in
                guard let self, self.task === t else { return }
                if error == nil {
                    self.store?.connected = true
                } else {
                    self.handleFailure(of: t)
                }
            }
        }
    }

    func disconnect() {
        stopped = true
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        store?.connected = false
    }

    /// Sends a command envelope: {"v":1,"cmd":...,"args":{...}}.
    func send(cmd: String, args: [String: Any] = [:]) {
        guard let task else { return }
        let envelope: [String: Any] = ["v": 1, "cmd": cmd, "args": args]
        guard let data = try? JSONSerialization.data(withJSONObject: envelope),
              let text = String(data: data, encoding: .utf8) else { return }
        task.send(.string(text)) { _ in }
    }

    // MARK: - Private

    private func receive(on t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            Task { @MainActor in
                guard let self, self.task === t else { return }
                switch result {
                case .success(let message):
                    self.store?.connected = true
                    switch message {
                    case .string(let s): self.decode(Data(s.utf8))
                    case .data(let d): self.decode(d)
                    @unknown default: break
                    }
                    self.receive(on: t)
                case .failure:
                    self.handleFailure(of: t)
                }
            }
        }
    }

    private func decode(_ data: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) else { return }
        if let event = obj as? [String: Any] {
            store?.handle(event)
        } else if let batch = obj as? [[String: Any]] {
            batch.forEach { store?.handle($0) }
        }
    }

    private func handleFailure(of t: URLSessionWebSocketTask) {
        guard task === t else { return }
        store?.connected = false
        task = nil
        guard !stopped, !reconnectPending else { return }
        reconnectPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            guard let self, !self.stopped else { return }
            self.connect()
        }
    }
}
