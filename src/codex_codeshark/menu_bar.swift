import Cocoa

final class CodesharkStatusBar: NSObject, NSApplicationDelegate {
    private let projectRoot: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let summaryItem = NSMenuItem(title: "Codeshark: starting", action: nil, keyEquivalent: "")

    init(projectRoot: String) {
        self.projectRoot = projectRoot
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

        if let button = statusItem.button {
            let image = mascotImage()
            image.isTemplate = true
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

    private func mascotImage() -> NSImage {
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: false) { _ in
            NSColor.black.setStroke()

            let body = NSBezierPath()
            body.move(to: NSPoint(x: 3.3, y: 9.2))
            body.curve(
                to: NSPoint(x: 12.4, y: 4.5),
                controlPoint1: NSPoint(x: 4.9, y: 5.8),
                controlPoint2: NSPoint(x: 8.6, y: 3.6)
            )
            body.curve(
                to: NSPoint(x: 17.1, y: 7.3),
                controlPoint1: NSPoint(x: 14.7, y: 4.7),
                controlPoint2: NSPoint(x: 17.2, y: 5.9)
            )
            body.curve(
                to: NSPoint(x: 12.1, y: 12.8),
                controlPoint1: NSPoint(x: 16.9, y: 9.5),
                controlPoint2: NSPoint(x: 14.6, y: 12.5)
            )
            body.curve(
                to: NSPoint(x: 3.3, y: 9.2),
                controlPoint1: NSPoint(x: 7.8, y: 13.7),
                controlPoint2: NSPoint(x: 4.5, y: 11.5)
            )
            self.stroke(body)

            let tail = NSBezierPath()
            tail.move(to: NSPoint(x: 3.8, y: 8.6))
            tail.line(to: NSPoint(x: 1.1, y: 5.5))
            tail.curve(
                to: NSPoint(x: 1.5, y: 9.0),
                controlPoint1: NSPoint(x: 1.4, y: 6.7),
                controlPoint2: NSPoint(x: 1.5, y: 7.9)
            )
            tail.curve(
                to: NSPoint(x: 1.1, y: 12.7),
                controlPoint1: NSPoint(x: 1.5, y: 10.3),
                controlPoint2: NSPoint(x: 1.4, y: 11.7)
            )
            tail.line(to: NSPoint(x: 4.0, y: 10.0))
            self.stroke(tail)

            let dorsal = NSBezierPath()
            dorsal.move(to: NSPoint(x: 7.3, y: 5.0))
            dorsal.curve(
                to: NSPoint(x: 8.6, y: 1.5),
                controlPoint1: NSPoint(x: 7.5, y: 3.3),
                controlPoint2: NSPoint(x: 7.9, y: 1.7)
            )
            dorsal.curve(
                to: NSPoint(x: 11.0, y: 4.2),
                controlPoint1: NSPoint(x: 9.7, y: 1.8),
                controlPoint2: NSPoint(x: 10.6, y: 3.1)
            )
            self.stroke(dorsal)

            let eye = NSBezierPath(ovalIn: NSRect(x: 12.0, y: 8.2, width: 2.1, height: 2.1))
            self.stroke(eye)

            let gills = NSBezierPath()
            for x in [7.2, 8.2, 9.2] {
                gills.move(to: NSPoint(x: x, y: 7.3))
                gills.curve(
                    to: NSPoint(x: x + 0.2, y: 9.8),
                    controlPoint1: NSPoint(x: x - 0.3, y: 8.1),
                    controlPoint2: NSPoint(x: x - 0.1, y: 9.2)
                )
            }
            self.stroke(gills)

            let mouth = NSBezierPath()
            mouth.move(to: NSPoint(x: 12.0, y: 7.0))
            mouth.curve(
                to: NSPoint(x: 15.4, y: 7.0),
                controlPoint1: NSPoint(x: 13.0, y: 6.6),
                controlPoint2: NSPoint(x: 14.4, y: 6.7)
            )
            self.stroke(mouth)

            let terminal = NSBezierPath()
            terminal.move(to: NSPoint(x: 11.4, y: 10.4))
            terminal.line(to: NSPoint(x: 12.2, y: 11.1))
            terminal.line(to: NSPoint(x: 11.4, y: 11.8))
            terminal.move(to: NSPoint(x: 12.8, y: 11.8))
            terminal.line(to: NSPoint(x: 13.9, y: 11.8))
            self.stroke(terminal)
            return true
        }
        image.isTemplate = true
        return image
    }

    private func stroke(_ path: NSBezierPath) {
        path.lineWidth = 1.35
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.stroke()
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 2 else {
    fputs("usage: CodesharkMenu PROJECT_ROOT\n", stderr)
    exit(64)
}
let app = NSApplication.shared
let delegate = CodesharkStatusBar(projectRoot: arguments[1])
app.delegate = delegate
app.run()
