import Cocoa
import SwiftUI

struct DashboardTask: Decodable, Identifiable {
    let id: String
    let project: String
    let phase: String
    let model: String
    let reasoningEffort: String
    let elapsedSeconds: Int

    enum CodingKeys: String, CodingKey {
        case id, project, phase, model
        case reasoningEffort = "reasoning_effort"
        case elapsedSeconds = "elapsed_seconds"
    }
}

struct DashboardFailure: Decodable {
    let taskID: String
    let message: String

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
        case message
    }
}

struct DashboardModelUsage: Decodable, Identifiable {
    let model: String
    let reasoningEffort: String
    let phase: String
    let runs: Int
    let completed: Int
    let elapsedSeconds: Double

    var id: String { "\(model)-\(reasoningEffort)-\(phase)" }

    enum CodingKeys: String, CodingKey {
        case model, phase, runs, completed
        case reasoningEffort = "reasoning_effort"
        case elapsedSeconds = "elapsed_seconds"
    }
}

struct DashboardSnapshot: Decodable {
    let state: String
    let activeTaskCount: Int
    let queueCount: Int
    let activeTasks: [DashboardTask]
    let recentArtifacts: [String]
    let lastFailure: DashboardFailure?
    let modelUsage: [DashboardModelUsage]

    static let empty = DashboardSnapshot(
        state: "starting",
        activeTaskCount: 0,
        queueCount: 0,
        activeTasks: [],
        recentArtifacts: [],
        lastFailure: nil,
        modelUsage: []
    )

    enum CodingKeys: String, CodingKey {
        case state
        case activeTaskCount = "active_task_count"
        case queueCount = "queue_count"
        case activeTasks = "active_tasks"
        case recentArtifacts = "recent_artifacts"
        case lastFailure = "last_failure"
        case modelUsage = "model_usage"
    }

    init(
        state: String,
        activeTaskCount: Int,
        queueCount: Int,
        activeTasks: [DashboardTask],
        recentArtifacts: [String],
        lastFailure: DashboardFailure?,
        modelUsage: [DashboardModelUsage]
    ) {
        self.state = state
        self.activeTaskCount = activeTaskCount
        self.queueCount = queueCount
        self.activeTasks = activeTasks
        self.recentArtifacts = recentArtifacts
        self.lastFailure = lastFailure
        self.modelUsage = modelUsage
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "starting"
        activeTaskCount = try container.decodeIfPresent(Int.self, forKey: .activeTaskCount) ?? 0
        queueCount = try container.decodeIfPresent(Int.self, forKey: .queueCount) ?? 0
        activeTasks = try container.decodeIfPresent([DashboardTask].self, forKey: .activeTasks) ?? []
        recentArtifacts = try container.decodeIfPresent([String].self, forKey: .recentArtifacts) ?? []
        lastFailure = try container.decodeIfPresent(DashboardFailure.self, forKey: .lastFailure)
        modelUsage = try container.decodeIfPresent([DashboardModelUsage].self, forKey: .modelUsage) ?? []
    }
}

final class DashboardModel: ObservableObject {
    @Published private(set) var snapshot = DashboardSnapshot.empty

    private let statusURL: URL

    init(projectRoot: String) {
        statusURL = URL(fileURLWithPath: projectRoot)
            .appendingPathComponent("runtime/menu-status.json")
    }

    func refresh() {
        guard let data = try? Data(contentsOf: statusURL),
              let snapshot = try? JSONDecoder().decode(DashboardSnapshot.self, from: data)
        else {
            return
        }
        self.snapshot = snapshot
    }
}

private func statusTitle(for snapshot: DashboardSnapshot) -> String {
    switch snapshot.state {
    case "working":
        return snapshot.activeTaskCount == 1 ? "Working" : "Working · \(snapshot.activeTaskCount) tasks"
    case "idle":
        return "Ready"
    default:
        return "Starting"
    }
}

private func statusColor(for snapshot: DashboardSnapshot) -> Color {
    switch snapshot.state {
    case "working":
        return .accentColor
    case "idle":
        return .green
    default:
        return .secondary
    }
}

private func elapsedText(_ seconds: Int) -> String {
    let minutes = max(0, seconds) / 60
    if minutes >= 60 {
        return "\(minutes / 60)h \(minutes % 60)m"
    }
    if minutes > 0 {
        return "\(minutes)m"
    }
    return "just now"
}

struct DashboardView: View {
    @ObservedObject var model: DashboardModel
    let openWorkspace: () -> Void
    let openLogs: () -> Void
    let quit: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "terminal.fill")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(.tint)
                    .frame(width: 30, height: 30)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 9))
                VStack(alignment: .leading, spacing: 3) {
                    Text("Codeshark")
                        .font(.headline)
                    HStack(spacing: 6) {
                        Circle()
                            .fill(statusColor(for: snapshot))
                            .frame(width: 7, height: 7)
                        Text(statusTitle(for: snapshot))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if snapshot.queueCount > 0 {
                    Text("Queue \(snapshot.queueCount)")
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.quaternary, in: Capsule())
                }
            }

            Divider()

            if snapshot.activeTasks.isEmpty {
                Label("Ready for a request", systemImage: "checkmark.circle")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("CURRENT WORK")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(snapshot.activeTasks) { task in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(task.phase)
                                    .font(.subheadline.weight(.semibold))
                                Spacer()
                                Text(elapsedText(task.elapsedSeconds))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text("\(task.project) · \(task.model) · \(task.reasoningEffort)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(10)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                    }
                }
            }

            if !snapshot.modelUsage.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    HStack {
                        Text("MODEL ACTIVITY")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("last 5h")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    ForEach(snapshot.modelUsage.prefix(3)) { usage in
                        HStack(spacing: 6) {
                            Text(usage.model.replacingOccurrences(of: "gpt-5.6-", with: ""))
                                .font(.caption.weight(.medium))
                            Text(usage.phase)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("\(usage.completed)/\(usage.runs) · \(Int(usage.elapsedSeconds / 60))m")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            if !snapshot.recentArtifacts.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("RECENT DELIVERY")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(snapshot.recentArtifacts, id: \.self) { artifact in
                        Label(artifact, systemImage: "doc")
                            .font(.caption)
                            .lineLimit(1)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let failure = snapshot.lastFailure {
                VStack(alignment: .leading, spacing: 5) {
                    Label("Last task needs attention", systemImage: "exclamationmark.triangle")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.orange)
                    Text(failure.message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                .padding(10)
                .background(Color.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
            }

            Divider()

            HStack(spacing: 8) {
                Button("Workspace", action: openWorkspace)
                    .buttonStyle(.bordered)
                Button("Logs", action: openLogs)
                    .buttonStyle(.bordered)
                Spacer()
                Button("Quit", role: .destructive, action: quit)
                    .buttonStyle(.bordered)
            }
        }
        .padding(14)
        .frame(width: 390)
    }
}

final class CodesharkStatusBar: NSObject, NSApplicationDelegate {
    private let projectRoot: String
    private let iconPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: 32)
    private let popover = NSPopover()
    private let dashboard: DashboardModel

    init(projectRoot: String, iconPath: String) {
        self.projectRoot = projectRoot
        self.iconPath = iconPath
        self.dashboard = DashboardModel(projectRoot: projectRoot)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(
            rootView: DashboardView(
                model: dashboard,
                openWorkspace: { [weak self] in self?.openWorkspace() },
                openLogs: { [weak self] in self?.openLogs() },
                quit: { [weak self] in self?.quitCodeshark() }
            )
        )

        if let button = statusItem.button {
            button.target = self
            button.action = #selector(togglePopover)
            button.toolTip = "Codeshark: starting"
            if let image = NSImage(contentsOfFile: iconPath) {
                image.isTemplate = false
                image.size = NSSize(width: 27, height: 18)
                button.image = image
            }
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
        dashboard.refresh()
        statusItem.button?.toolTip = "Codeshark: \(statusTitle(for: dashboard.snapshot).lowercased())"
    }

    @objc private func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            dashboard.refresh()
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        }
    }

    @objc private func openWorkspace() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("workspace"))
    }

    @objc private func openLogs() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("runtime"))
    }

    @objc private func quitCodeshark() {
        let launchAgents = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents")
        let command = Process()
        command.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        command.arguments = [
            "bootout",
            "gui/\(getuid())",
            launchAgents.appendingPathComponent("com.codeshark.agent.plist").path,
            launchAgents.appendingPathComponent("com.codeshark.status.plist").path,
        ]
        try? command.run()
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
