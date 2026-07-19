import Cocoa

final class CodesharkStatusBar: NSObject, NSApplicationDelegate {
    private let projectRoot: String
    private let iconPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let summaryItem = NSMenuItem(title: "Codeshark: starting", action: nil, keyEquivalent: "")

    init(projectRoot: String, iconPath: String) {
        self.projectRoot = projectRoot
        self.iconPath = iconPath
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        let menu = NSMenu()
        summaryItem.isEnabled = false
        menu.addItem(summaryItem)
        menu.addItem(.separator())
        menu.addItem(withTitle: "Open Workspace", action: #selector(openWorkspace), keyEquivalent: "")
        menu.addItem(withTitle: "Open Service Logs", action: #selector(openLogs), keyEquivalent: "")
        statusItem.menu = menu

        if let button = statusItem.button,
           let image = NSImage(contentsOfFile: iconPath) {
            image.isTemplate = true
            image.size = NSSize(width: 22, height: 17.7)
            button.image = image
            button.toolTip = "Codeshark: starting"
        }

        refreshStatus()
        Timer.scheduledTimer(
            timeInterval: 2,
            target: self,
            selector: #selector(refreshStatus),
            userInfo: nil,
            repeats: true
        )
    }

    @objc private func refreshStatus() {
        let statusPath = URL(fileURLWithPath: projectRoot)
            .appendingPathComponent("runtime/menu-status.json")
        var state = "starting"
        var activeCount = 0
        if let data = try? Data(contentsOf: statusPath),
           let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            state = payload["state"] as? String ?? "idle"
            activeCount = payload["active_task_count"] as? Int ?? 0
        }
        let description: String
        if state == "working" {
            description = activeCount == 1
                ? "Codeshark: working"
                : "Codeshark: working (\(activeCount) tasks)"
        } else if state == "idle" {
            description = "Codeshark: ready"
        } else {
            description = "Codeshark: starting"
        }
        summaryItem.title = description
        statusItem.button?.toolTip = description
    }

    @objc private func openWorkspace() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("workspace"))
    }

    @objc private func openLogs() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("runtime"))
    }

}

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    fputs("usage: CodesharkMenu PROJECT_ROOT ICON_PATH\n", stderr)
    exit(64)
}
let app = NSApplication.shared
let delegate = CodesharkStatusBar(projectRoot: arguments[1], iconPath: arguments[2])
app.delegate = delegate
app.run()
