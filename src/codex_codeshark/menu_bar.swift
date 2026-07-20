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

struct DashboardModelAssignment: Decodable, Identifiable {
    let model: String
    let reasoningEffort: String
    let role: String

    var id: String { "\(model)-\(reasoningEffort)-\(role)" }

    enum CodingKeys: String, CodingKey {
        case model, role
        case reasoningEffort = "reasoning_effort"
    }
}

struct DashboardActivityLog: Decodable, Identifiable {
    let id: String
    let phase: String
    let model: String
    let reasoningEffort: String
    let elapsedSeconds: Double
    let outcome: String
    let finishedAt: Int

    enum CodingKeys: String, CodingKey {
        case id, phase, model, outcome
        case reasoningEffort = "reasoning_effort"
        case elapsedSeconds = "elapsed_seconds"
        case finishedAt = "finished_at"
    }
}

struct DashboardSnapshot: Decodable {
    let state: String
    let activeTaskCount: Int
    let queueCount: Int
    let workspacePath: String
    let modelAssignments: [DashboardModelAssignment]
    let activeTasks: [DashboardTask]
    let recentArtifacts: [String]
    let lastFailure: DashboardFailure?
    let activityLog: [DashboardActivityLog]

    static let empty = DashboardSnapshot(
        state: "starting",
        activeTaskCount: 0,
        queueCount: 0,
        workspacePath: "",
        modelAssignments: [],
        activeTasks: [],
        recentArtifacts: [],
        lastFailure: nil,
        activityLog: []
    )

    enum CodingKeys: String, CodingKey {
        case state
        case activeTaskCount = "active_task_count"
        case queueCount = "queue_count"
        case workspacePath = "workspace_path"
        case modelAssignments = "model_assignments"
        case activeTasks = "active_tasks"
        case recentArtifacts = "recent_artifacts"
        case lastFailure = "last_failure"
        case activityLog = "activity_log"
    }

    init(
        state: String,
        activeTaskCount: Int,
        queueCount: Int,
        workspacePath: String,
        modelAssignments: [DashboardModelAssignment],
        activeTasks: [DashboardTask],
        recentArtifacts: [String],
        lastFailure: DashboardFailure?,
        activityLog: [DashboardActivityLog]
    ) {
        self.state = state
        self.activeTaskCount = activeTaskCount
        self.queueCount = queueCount
        self.workspacePath = workspacePath
        self.modelAssignments = modelAssignments
        self.activeTasks = activeTasks
        self.recentArtifacts = recentArtifacts
        self.lastFailure = lastFailure
        self.activityLog = activityLog
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "starting"
        activeTaskCount = try container.decodeIfPresent(Int.self, forKey: .activeTaskCount) ?? 0
        queueCount = try container.decodeIfPresent(Int.self, forKey: .queueCount) ?? 0
        workspacePath = try container.decodeIfPresent(String.self, forKey: .workspacePath) ?? ""
        modelAssignments = try container.decodeIfPresent([DashboardModelAssignment].self, forKey: .modelAssignments) ?? []
        activeTasks = try container.decodeIfPresent([DashboardTask].self, forKey: .activeTasks) ?? []
        recentArtifacts = try container.decodeIfPresent([String].self, forKey: .recentArtifacts) ?? []
        lastFailure = try container.decodeIfPresent(DashboardFailure.self, forKey: .lastFailure)
        activityLog = try container.decodeIfPresent([DashboardActivityLog].self, forKey: .activityLog) ?? []
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

private func compactModelName(_ model: String) -> String {
    model.replacingOccurrences(of: "gpt-5.6-", with: "")
}

private func workspaceDisplayPath(_ path: String) -> String {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    guard path.hasPrefix(home) else { return path }
    return "~" + path.dropFirst(home.count)
}

private func phaseTitle(_ phase: String) -> String {
    phase.replacingOccurrences(of: "-", with: " ").localizedCapitalized
}

private func activityIcon(_ outcome: String) -> String {
    switch outcome {
    case "completed":
        return "checkmark.circle.fill"
    case "cancelled", "timed out":
        return "pause.circle.fill"
    default:
        return "xmark.circle.fill"
    }
}

private func activityColor(_ outcome: String) -> Color {
    switch outcome {
    case "completed":
        return .green
    case "cancelled", "timed out":
        return .orange
    default:
        return .red
    }
}

private func timeAgoText(_ timestamp: Int) -> String {
    let elapsed = max(0, Int(Date().timeIntervalSince1970) - timestamp)
    if elapsed >= 3600 {
        return "\(elapsed / 3600)h ago"
    }
    if elapsed >= 60 {
        return "\(elapsed / 60)m ago"
    }
    return "now"
}

struct ExecutionLogView: View {
    @ObservedObject var model: DashboardModel
    let revealLogFolder: () -> Void
    let close: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Execution Log")
                    .font(.headline)
                Text("Recent model phases")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if snapshot.activityLog.isEmpty {
                        Label("No execution phases recorded yet", systemImage: "text.alignleft")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(snapshot.activityLog) { entry in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: activityIcon(entry.outcome))
                                    .font(.subheadline)
                                    .foregroundStyle(activityColor(entry.outcome))
                                    .padding(.top, 2)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("\(phaseTitle(entry.phase)) · \(compactModelName(entry.model))")
                                        .font(.subheadline.weight(.medium))
                                    Text("\(entry.outcome) · \(entry.reasoningEffort) · \(elapsedText(Int(entry.elapsedSeconds)))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(timeAgoText(entry.finishedAt))
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
            }

            Divider()

            HStack {
                Button("Reveal Files", action: revealLogFolder)
                    .buttonStyle(.bordered)
                Spacer()
                Button("Close", action: close)
                    .buttonStyle(.bordered)
            }
        }
        .padding(16)
        .frame(width: 380, height: 360)
    }
}

struct DashboardView: View {
    @ObservedObject var model: DashboardModel
    let chooseWorkspace: () -> Void
    let configureModels: () -> Void
    let showLogs: () -> Void
    let close: () -> Void
    let quit: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
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

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if !snapshot.modelAssignments.isEmpty {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Text("MODEL ROUTING")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Button("Configure…", action: configureModels)
                                    .buttonStyle(.borderless)
                                    .font(.caption)
                            }
                            ForEach(snapshot.modelAssignments) { assignment in
                                HStack(spacing: 6) {
                                    Text(compactModelName(assignment.model))
                                        .font(.caption.weight(.semibold))
                                    Text(assignment.role)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text(assignment.reasoningEffort)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.tertiary)
                                }
                            }
                        }
                    }

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
                }
            }

            Divider()

            HStack(spacing: 8) {
                Button("Workspace…", action: chooseWorkspace)
                    .buttonStyle(.bordered)
                Button("Logs", action: showLogs)
                    .buttonStyle(.bordered)
                Spacer()
                Button("Close", action: close)
                    .buttonStyle(.bordered)
                Button("Quit", role: .destructive, action: quit)
                    .buttonStyle(.bordered)
            }
        }
        .padding(14)
        .frame(width: 340, height: 320)
    }
}

final class CodesharkStatusBar: NSObject, NSApplicationDelegate {
    private let projectRoot: String
    private let iconPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: 32)
    private let popover = NSPopover()
    private let dashboard: DashboardModel
    private var logPanel: NSPanel?

    init(projectRoot: String, iconPath: String) {
        self.projectRoot = projectRoot
        self.iconPath = iconPath
        self.dashboard = DashboardModel(projectRoot: projectRoot)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 340, height: 320)
        popover.contentViewController = NSHostingController(
            rootView: DashboardView(
                model: dashboard,
                chooseWorkspace: { [weak self] in self?.chooseWorkspace() },
                configureModels: { [weak self] in self?.configureModels() },
                showLogs: { [weak self] in self?.showLogs() },
                close: { [weak self] in self?.closePopover() },
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

    private func chooseWorkspace() {
        dashboard.refresh()
        let chooser = NSOpenPanel()
        chooser.canChooseFiles = false
        chooser.canChooseDirectories = true
        chooser.allowsMultipleSelection = false
        chooser.message = "Choose the folder Codeshark should use for new work."
        if !dashboard.snapshot.workspacePath.isEmpty {
            chooser.directoryURL = URL(fileURLWithPath: dashboard.snapshot.workspacePath)
        }
        guard chooser.runModal() == .OK, let directory = chooser.url else { return }

        let confirmation = NSAlert()
        confirmation.messageText = "Use this workspace?"
        confirmation.informativeText = workspaceDisplayPath(directory.path)
            + "\n\nCodeshark will restart to apply the change. Active work is safely returned to the queue."
        confirmation.addButton(withTitle: "Set Workspace")
        confirmation.addButton(withTitle: "Cancel")
        guard confirmation.runModal() == .alertFirstButtonReturn else { return }

        runServiceCommand(["set-workspace", directory.path])
    }

    private func configureModels() {
        dashboard.refresh()
        let alert = NSAlert()
        alert.messageText = "Model Routing"
        alert.informativeText = "Choose the model assigned to each role. Codeshark restarts to apply the changes."
        alert.addButton(withTitle: "Apply")
        alert.addButton(withTitle: "Cancel")

        let routine = modelPicker(currentModel(for: "Routine", fallback: "gpt-5.6-luna"))
        let preflight = modelPicker(currentModel(for: "Preflight", fallback: "gpt-5.6-luna"))
        let primary = modelPicker(currentModel(for: "Primary · Rework", fallback: "gpt-5.6-sol"))
        let validator = modelPicker(currentModel(for: "Validation · Feedback", fallback: "gpt-5.6-terra"))
        let form = NSStackView(views: [
            modelRow("Routine", picker: routine),
            modelRow("Preflight", picker: preflight),
            modelRow("Primary / Rework", picker: primary),
            modelRow("Validation / Feedback", picker: validator),
        ])
        form.orientation = .vertical
        form.spacing = 8
        form.edgeInsets = NSEdgeInsets(top: 4, left: 0, bottom: 0, right: 0)
        alert.accessoryView = form
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        runServiceCommand([
            "set-models",
            "--routine", routine.titleOfSelectedItem ?? "gpt-5.6-luna",
            "--preflight", preflight.titleOfSelectedItem ?? "gpt-5.6-luna",
            "--primary", primary.titleOfSelectedItem ?? "gpt-5.6-sol",
            "--validator", validator.titleOfSelectedItem ?? "gpt-5.6-terra",
        ])
    }

    private func modelPicker(_ current: String) -> NSPopUpButton {
        let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 165, height: 26), pullsDown: false)
        var models = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
        if !models.contains(current) {
            models.insert(current, at: 0)
        }
        picker.addItems(withTitles: models)
        picker.selectItem(withTitle: current)
        return picker
    }

    private func modelRow(_ title: String, picker: NSPopUpButton) -> NSStackView {
        let label = NSTextField(labelWithString: title)
        label.frame = NSRect(x: 0, y: 0, width: 130, height: 20)
        label.setContentHuggingPriority(.required, for: .horizontal)
        let row = NSStackView(views: [label, picker])
        row.orientation = .horizontal
        row.spacing = 10
        return row
    }

    private func currentModel(for role: String, fallback: String) -> String {
        dashboard.snapshot.modelAssignments.first(where: { $0.role == role })?.model ?? fallback
    }

    private func showLogs() {
        dashboard.refresh()
        if let panel = logPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 360),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Execution Log"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.contentViewController = NSHostingController(
            rootView: ExecutionLogView(
                model: dashboard,
                revealLogFolder: { [weak self] in self?.revealLogFolder() },
                close: { [weak self] in self?.logPanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        logPanel = panel
    }

    private func revealLogFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("runtime"))
    }

    private func closePopover() {
        popover.performClose(nil)
    }

    private func runServiceCommand(_ arguments: [String]) {
        guard let python = servicePython() else {
            showError("Could not find the Codeshark service Python runtime.")
            return
        }
        let command = Process()
        let output = Pipe()
        command.executableURL = URL(fileURLWithPath: python)
        command.arguments = ["-m", "codex_codeshark"] + arguments
        command.environment = [
            "PYTHONPATH": deployedSourceRoot(),
            "CODEX_CODESHARK_HOME": projectRoot,
            "TELEGRAM_CODEX_CONFIG": URL(fileURLWithPath: projectRoot)
                .appendingPathComponent("config.local.toml").path,
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        ]
        command.standardOutput = output
        command.standardError = output
        do {
            try command.run()
            command.waitUntilExit()
        } catch {
            showError("Could not apply the setting: \(error.localizedDescription)")
            return
        }
        if command.terminationStatus != 0 {
            let detail = String(
                data: output.fileHandleForReading.readDataToEndOfFile(),
                encoding: .utf8
            ) ?? ""
            showError(detail.isEmpty ? "Could not apply the setting." : detail)
        }
    }

    private func deployedSourceRoot() -> String {
        URL(fileURLWithPath: CommandLine.arguments[0])
            .deletingLastPathComponent()
            .appendingPathComponent("src")
            .path
    }

    private func servicePython() -> String? {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/com.codeshark.agent.plist")
        guard let data = try? Data(contentsOf: plist),
              let payload = try? PropertyListSerialization.propertyList(from: data, format: nil),
              let dictionary = payload as? [String: Any],
              let arguments = dictionary["ProgramArguments"] as? [String],
              let python = arguments.first,
              FileManager.default.isExecutableFile(atPath: python)
        else {
            return nil
        }
        return python
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Codeshark"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
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
