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

private struct CodexReasoningLevel: Decodable {
    let effort: String
}

private struct CodexCachedModel: Decodable {
    let slug: String
    let visibility: String
    let supportedReasoningLevels: [CodexReasoningLevel]

    enum CodingKeys: String, CodingKey {
        case slug, visibility
        case supportedReasoningLevels = "supported_reasoning_levels"
    }
}

private struct CodexModelCache: Decodable {
    let models: [CodexCachedModel]
}

private struct CodexModelOption {
    let slug: String
    let reasoningEfforts: [String]
}

private let fallbackModelOptions = [
    CodexModelOption(slug: "gpt-5.6-sol", reasoningEfforts: ["low", "medium", "high", "xhigh", "max", "ultra"]),
    CodexModelOption(slug: "gpt-5.6-terra", reasoningEfforts: ["low", "medium", "high", "xhigh", "max", "ultra"]),
    CodexModelOption(slug: "gpt-5.6-luna", reasoningEfforts: ["low", "medium", "high", "xhigh", "max"]),
    CodexModelOption(slug: "gpt-5.5", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
    CodexModelOption(slug: "gpt-5.4", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
    CodexModelOption(slug: "gpt-5.4-mini", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
    CodexModelOption(slug: "gpt-5.4-nano", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
    CodexModelOption(slug: "gpt-5.3-codex-spark", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
    CodexModelOption(slug: "gpt-5.2", reasoningEfforts: ["low", "medium", "high", "xhigh"]),
]

private func availableModelOptions() -> [CodexModelOption] {
    let cacheURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".codex/models_cache.json")
    let cached = (try? Data(contentsOf: cacheURL))
        .flatMap { try? JSONDecoder().decode(CodexModelCache.self, from: $0) }?.models ?? []
    let cachedBySlug = Dictionary(uniqueKeysWithValues: cached.map { ($0.slug, $0) })
    var options: [CodexModelOption] = []
    var seen = Set<String>()
    for fallback in fallbackModelOptions {
        let efforts = cachedBySlug[fallback.slug]?.supportedReasoningLevels.map(\.effort)
        options.append(CodexModelOption(slug: fallback.slug, reasoningEfforts: efforts ?? fallback.reasoningEfforts))
        seen.insert(fallback.slug)
    }
    for model in cached where model.visibility == "list" && seen.insert(model.slug).inserted {
        options.append(
            CodexModelOption(
                slug: model.slug,
                reasoningEfforts: model.supportedReasoningLevels.map(\.effort)
            )
        )
    }
    return options
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
    let modelUsage5h: [DashboardModelUsage]
    let modelUsage7d: [DashboardModelUsage]

    static let empty = DashboardSnapshot(
        state: "starting",
        activeTaskCount: 0,
        queueCount: 0,
        workspacePath: "",
        modelAssignments: [],
        activeTasks: [],
        recentArtifacts: [],
        lastFailure: nil,
        activityLog: [],
        modelUsage5h: [],
        modelUsage7d: []
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
        case modelUsage5h = "model_usage_5h"
        case modelUsage7d = "model_usage_7d"
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
        activityLog: [DashboardActivityLog],
        modelUsage5h: [DashboardModelUsage],
        modelUsage7d: [DashboardModelUsage]
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
        self.modelUsage5h = modelUsage5h
        self.modelUsage7d = modelUsage7d
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
        modelUsage5h = try container.decodeIfPresent([DashboardModelUsage].self, forKey: .modelUsage5h) ?? []
        modelUsage7d = try container.decodeIfPresent([DashboardModelUsage].self, forKey: .modelUsage7d) ?? []
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

private struct ModelUsageGroup: Identifiable {
    let model: String
    let reasoningEffort: String
    let runs: Int
    let completed: Int
    let elapsedSeconds: Double

    var id: String { "\(model)-\(reasoningEffort)" }
}

struct ModelUsageView: View {
    @ObservedObject var model: DashboardModel
    let close: () -> Void
    @State private var period = 0

    private var entries: [DashboardModelUsage] {
        period == 0 ? model.snapshot.modelUsage5h : model.snapshot.modelUsage7d
    }

    private var groups: [ModelUsageGroup] {
        let grouped = Dictionary(grouping: entries) {
            "\($0.model)-\($0.reasoningEffort)"
        }
        return grouped.values.map { entries in
            ModelUsageGroup(
                model: entries[0].model,
                reasoningEffort: entries[0].reasoningEffort,
                runs: entries.reduce(0) { $0 + $1.runs },
                completed: entries.reduce(0) { $0 + $1.completed },
                elapsedSeconds: entries.reduce(0) { $0 + $1.elapsedSeconds }
            )
        }
        .sorted { $0.elapsedSeconds > $1.elapsedSeconds }
    }

    private var totalElapsedSeconds: Double {
        groups.reduce(0) { $0 + $1.elapsedSeconds }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Model Usage")
                    .font(.headline)
                Text("Recorded execution contribution, not account quota.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Picker("Period", selection: $period) {
                Text("Last 5 hours").tag(0)
                Text("Last 7 days").tag(1)
            }
            .pickerStyle(.segmented)

            ScrollView {
                VStack(alignment: .leading, spacing: 11) {
                    if groups.isEmpty {
                        Label("No recorded model phases", systemImage: "chart.bar")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(groups) { group in
                            let share = totalElapsedSeconds > 0
                                ? Int((group.elapsedSeconds / totalElapsedSeconds * 100).rounded())
                                : 0
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(compactModelName(group.model))
                                        .font(.subheadline.weight(.semibold))
                                    Text(group.reasoningEffort)
                                        .font(.caption.monospaced())
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(share)%")
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                                Text("\(group.runs) phases · \(group.completed) completed · \(elapsedText(Int(group.elapsedSeconds)))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                ProgressView(value: totalElapsedSeconds > 0 ? group.elapsedSeconds / totalElapsedSeconds : 0)
                            }
                            .padding(10)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
            }

            Divider()

            HStack {
                Text("Quota attribution is not exposed by Codex.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                Spacer()
                Button("Close", action: close)
                    .buttonStyle(.bordered)
            }
        }
        .padding(16)
        .frame(width: 430, height: 410)
    }
}

final class CodesharkStatusBar: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate {
    private let projectRoot: String
    private let iconPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: 32)
    private let menu = NSMenu()
    private let dashboard: DashboardModel
    private var logPanel: NSPanel?
    private var usagePanel: NSPanel?
    private var modelRoutingPanel: NSPanel?
    private var modelPickers: [String: NSPopUpButton] = [:]
    private var reasoningPickers: [String: NSPopUpButton] = [:]
    private var modelOptions: [CodexModelOption] = []

    init(projectRoot: String, iconPath: String) {
        self.projectRoot = projectRoot
        self.iconPath = iconPath
        self.dashboard = DashboardModel(projectRoot: projectRoot)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        menu.delegate = self
        statusItem.menu = menu

        if let button = statusItem.button {
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

    func menuNeedsUpdate(_ menu: NSMenu) {
        dashboard.refresh()
        rebuildMenu()
    }

    private func rebuildMenu() {
        menu.removeAllItems()
        let snapshot = dashboard.snapshot

        let status = NSMenuItem(
            title: "Codeshark is \(statusTitle(for: snapshot).lowercased())",
            action: #selector(ignoreMenuItem(_:)),
            keyEquivalent: ""
        )
        status.target = self
        status.attributedTitle = NSAttributedString(
            string: "● Codeshark is \(statusTitle(for: snapshot).lowercased())",
            attributes: [
                .font: NSFont.systemFont(ofSize: 14, weight: .semibold),
                .foregroundColor: statusMenuColor(for: snapshot),
            ]
        )
        menu.addItem(status)
        menu.addItem(.separator())

        addSection("Running", to: menu)
        if snapshot.activeTasks.isEmpty {
            addSecondary("Ready", to: menu)
        } else {
            for task in snapshot.activeTasks.prefix(2) {
                addStatic(phaseTitle(task.phase), to: menu)
                addSecondary(
                    "\(task.project) · \(compactModelName(task.model)) · \(task.reasoningEffort) · \(elapsedText(task.elapsedSeconds))",
                    to: menu
                )
            }
            if snapshot.activeTasks.count > 2 {
                addSecondary("\(snapshot.activeTasks.count - 2) more task(s) running", to: menu)
            }
        }

        menu.addItem(.separator())
        addSection("Recent", to: menu)
        if snapshot.recentArtifacts.isEmpty {
            addSecondary("No recent delivery", to: menu)
        } else {
            for artifact in snapshot.recentArtifacts.prefix(3) {
                addStatic(artifact, to: menu)
            }
        }

        if let failure = snapshot.lastFailure {
            menu.addItem(.separator())
            addSection("Last Task", to: menu)
            addSecondary(failure.message, to: menu)
        }

        menu.addItem(.separator())
        menu.addItem(actionItem("Model Routing…", action: #selector(openModelRouting(_:))))
        menu.addItem(usageMenuItem(snapshot: snapshot))
        menu.addItem(actionItem("Workspace…", action: #selector(openWorkspace(_:))))
        menu.addItem(actionItem("Logs…", action: #selector(openLogs(_:))))

        menu.addItem(.separator())
        menu.addItem(actionItem("Close Menu", action: #selector(closeMenu(_:))))
        menu.addItem(.separator())

        let quit = actionItem("Quit Codeshark", action: #selector(quitCodeshark))
        quit.attributedTitle = NSAttributedString(
            string: "Quit Codeshark",
            attributes: [
                .font: NSFont.systemFont(ofSize: 14, weight: .medium),
                .foregroundColor: NSColor.systemRed,
            ]
        )
        menu.addItem(quit)
    }

    private func addSection(_ title: String, to target: NSMenu) {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.isEnabled = false
        item.attributedTitle = NSAttributedString(
            string: title,
            attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
                .foregroundColor: NSColor.secondaryLabelColor,
            ]
        )
        target.addItem(item)
    }

    private func addStatic(_ title: String, to target: NSMenu) {
        let item = NSMenuItem(title: title, action: #selector(ignoreMenuItem(_:)), keyEquivalent: "")
        item.target = self
        target.addItem(item)
    }

    private func addSecondary(_ title: String, to target: NSMenu) {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.isEnabled = false
        item.attributedTitle = NSAttributedString(
            string: title,
            attributes: [
                .font: NSFont.systemFont(ofSize: 12),
                .foregroundColor: NSColor.secondaryLabelColor,
            ]
        )
        target.addItem(item)
    }

    private func actionItem(_ title: String, action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        return item
    }

    private func usageMenuItem(snapshot: DashboardSnapshot) -> NSMenuItem {
        let item = NSMenuItem(title: "Usage", action: nil, keyEquivalent: "")
        let usage = NSMenu(title: "Usage")
        let recent = snapshot.modelUsage5h.reduce(0) { $0 + $1.runs }
        let weekly = snapshot.modelUsage7d.reduce(0) { $0 + $1.runs }
        addSecondary("Last 5 hours · \(recent) phases", to: usage)
        addSecondary("Last 7 days · \(weekly) phases", to: usage)
        usage.addItem(.separator())
        usage.addItem(actionItem("Open Usage…", action: #selector(openUsage(_:))))
        item.submenu = usage
        return item
    }

    private func statusMenuColor(for snapshot: DashboardSnapshot) -> NSColor {
        switch snapshot.state {
        case "working":
            return .systemBlue
        case "idle":
            return .systemGreen
        default:
            return .secondaryLabelColor
        }
    }

    @objc private func ignoreMenuItem(_ sender: Any?) {}

    @objc private func openModelRouting(_ sender: Any?) {
        configureModels()
    }

    @objc private func openWorkspace(_ sender: Any?) {
        chooseWorkspace()
    }

    @objc private func openUsage(_ sender: Any?) {
        showUsage()
    }

    @objc private func openLogs(_ sender: Any?) {
        showLogs()
    }

    @objc private func closeMenu(_ sender: Any?) {
        menu.cancelTracking()
    }

    private func chooseWorkspace() {
        dashboard.refresh()
        let chooser = NSOpenPanel()
        chooser.canChooseFiles = false
        chooser.canChooseDirectories = true
        chooser.allowsMultipleSelection = false
        chooser.message = "Choose Codeshark's working directory for new work."
        if !dashboard.snapshot.workspacePath.isEmpty {
            chooser.directoryURL = URL(fileURLWithPath: dashboard.snapshot.workspacePath)
        }
        guard chooser.runModal() == .OK, let directory = chooser.url else { return }

        let confirmation = NSAlert()
        confirmation.messageText = "Set Codeshark workspace?"
        confirmation.informativeText = workspaceDisplayPath(directory.path)
            + "\n\nThis changes Codeshark's working directory for new tasks. Codeshark will restart to apply it; active work is safely returned to the queue."
        confirmation.addButton(withTitle: "Set Workspace")
        confirmation.addButton(withTitle: "Cancel")
        guard confirmation.runModal() == .alertFirstButtonReturn else { return }

        runServiceCommand(["set-workspace", directory.path])
    }

    private func configureModels() {
        dashboard.refresh()
        if let panel = modelRoutingPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 400),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Model Routing"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self

        let content = NSView(frame: panel.contentView?.bounds ?? .zero)
        let title = NSTextField(labelWithString: "Model Routing")
        title.font = .systemFont(ofSize: 17, weight: .semibold)
        title.frame = NSRect(x: 20, y: 347, width: 580, height: 24)
        content.addSubview(title)

        let detail = NSTextField(wrappingLabelWithString: "Choose a model and a supported reasoning effort for each role. Applying restarts Codeshark.")
        detail.font = .systemFont(ofSize: 13)
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 20, y: 305, width: 580, height: 34)
        content.addSubview(detail)

        let modelHeader = NSTextField(labelWithString: "MODEL")
        modelHeader.font = .systemFont(ofSize: 11, weight: .semibold)
        modelHeader.textColor = .secondaryLabelColor
        modelHeader.frame = NSRect(x: 185, y: 278, width: 235, height: 16)
        content.addSubview(modelHeader)
        let effortHeader = NSTextField(labelWithString: "REASONING")
        effortHeader.font = .systemFont(ofSize: 11, weight: .semibold)
        effortHeader.textColor = .secondaryLabelColor
        effortHeader.frame = NSRect(x: 430, y: 278, width: 170, height: 16)
        content.addSubview(effortHeader)

        let roles = [
            ("Routine", "Routine", "gpt-5.6-luna", "medium"),
            ("Preflight", "Preflight", "gpt-5.6-luna", "low"),
            ("Primary", "Primary", "gpt-5.6-sol", "high"),
            ("Rework", "Rework", "gpt-5.6-sol", "high"),
            ("Validation / Feedback", "Validation · Feedback", "gpt-5.6-terra", "high"),
        ]
        modelOptions = availableModelOptions()
        modelPickers = [:]
        reasoningPickers = [:]
        for (index, role) in roles.enumerated() {
            let y = 235 - (index * 38)
            let label = NSTextField(labelWithString: role.0)
            label.font = .systemFont(ofSize: 13, weight: .medium)
            label.frame = NSRect(x: 20, y: y + 4, width: 155, height: 20)
            content.addSubview(label)

            let current = dashboard.snapshot.modelAssignments
                .first(where: { $0.role == role.1 })?.model ?? role.2
            let currentEffort = dashboard.snapshot.modelAssignments
                .first(where: { $0.role == role.1 })?.reasoningEffort ?? role.3
            let modelPicker = modelPicker(
                current,
                role: role.1,
                frame: NSRect(x: 185, y: y, width: 235, height: 28)
            )
            let effortPicker = reasoningPicker(
                model: current,
                current: currentEffort,
                frame: NSRect(x: 430, y: y, width: 170, height: 28)
            )
            content.addSubview(modelPicker)
            content.addSubview(effortPicker)
            modelPickers[role.1] = modelPicker
            reasoningPickers[role.1] = effortPicker
        }

        let separator = NSBox(frame: NSRect(x: 20, y: 53, width: 580, height: 1))
        separator.boxType = .separator
        content.addSubview(separator)

        let close = NSButton(title: "Close", target: self, action: #selector(closeModelRouting))
        close.bezelStyle = .rounded
        close.frame = NSRect(x: 20, y: 15, width: 90, height: 28)
        content.addSubview(close)

        let apply = NSButton(title: "Apply", target: self, action: #selector(applyModelRouting))
        apply.bezelStyle = .rounded
        apply.keyEquivalent = "\r"
        apply.frame = NSRect(x: 510, y: 15, width: 90, height: 28)
        content.addSubview(apply)

        panel.contentView = content
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        modelRoutingPanel = panel
    }

    private func modelPicker(_ current: String, role: String, frame: NSRect) -> NSPopUpButton {
        let picker = NSPopUpButton(frame: frame, pullsDown: false)
        var options = modelOptions
        if !options.contains(where: { $0.slug == current }) {
            options.insert(
                CodexModelOption(
                    slug: current,
                    reasoningEfforts: ["low", "medium", "high", "xhigh", "max", "ultra"]
                ),
                at: 0
            )
        }
        for option in options {
            picker.addItem(withTitle: option.slug)
            picker.lastItem?.representedObject = option.slug
        }
        picker.selectItem(at: options.firstIndex(where: { $0.slug == current }) ?? 0)
        picker.identifier = NSUserInterfaceItemIdentifier(role)
        picker.target = self
        picker.action = #selector(modelSelectionChanged(_:))
        return picker
    }

    private func reasoningPicker(model: String, current: String, frame: NSRect) -> NSPopUpButton {
        let picker = NSPopUpButton(frame: frame, pullsDown: false)
        configureReasoningPicker(picker, model: model, current: current)
        return picker
    }

    private func configureReasoningPicker(_ picker: NSPopUpButton, model: String, current: String?) {
        let option = modelOptions.first(where: { $0.slug == model })
        let efforts = option?.reasoningEfforts ?? ["low", "medium", "high", "xhigh", "max", "ultra"]
        picker.removeAllItems()
        picker.addItems(withTitles: efforts)
        let selected = current.flatMap { efforts.contains($0) ? $0 : nil } ?? efforts.first ?? "medium"
        picker.selectItem(withTitle: selected)
    }

    private func selectedModel(_ picker: NSPopUpButton) -> String? {
        picker.selectedItem?.representedObject as? String ?? picker.titleOfSelectedItem
    }

    @objc private func modelSelectionChanged(_ sender: NSPopUpButton) {
        guard let role = sender.identifier?.rawValue,
              let model = selectedModel(sender),
              let effortPicker = reasoningPickers[role]
        else {
            return
        }
        configureReasoningPicker(effortPicker, model: model, current: effortPicker.titleOfSelectedItem)
    }

    @objc private func closeModelRouting() {
        modelRoutingPanel?.orderOut(nil)
    }

    @objc private func applyModelRouting() {
        guard let routinePicker = modelPickers["Routine"],
              let routine = selectedModel(routinePicker),
              let routineEffort = reasoningPickers["Routine"]?.titleOfSelectedItem,
              let preflightPicker = modelPickers["Preflight"],
              let preflight = selectedModel(preflightPicker),
              let preflightEffort = reasoningPickers["Preflight"]?.titleOfSelectedItem,
              let primaryPicker = modelPickers["Primary"],
              let primary = selectedModel(primaryPicker),
              let primaryEffort = reasoningPickers["Primary"]?.titleOfSelectedItem,
              let reworkPicker = modelPickers["Rework"],
              let rework = selectedModel(reworkPicker),
              let reworkEffort = reasoningPickers["Rework"]?.titleOfSelectedItem,
              let validatorPicker = modelPickers["Validation · Feedback"],
              let validator = selectedModel(validatorPicker),
              let validatorEffort = reasoningPickers["Validation · Feedback"]?.titleOfSelectedItem
        else {
            showError("Could not read the selected model routing.")
            return
        }
        modelRoutingPanel?.orderOut(nil)
        runServiceCommand([
            "set-models",
            "--routine", routine,
            "--routine-effort", routineEffort,
            "--preflight", preflight,
            "--preflight-effort", preflightEffort,
            "--primary", primary,
            "--primary-effort", primaryEffort,
            "--rework", rework,
            "--rework-effort", reworkEffort,
            "--validator", validator,
            "--validator-effort", validatorEffort,
        ])
    }

    private func showUsage() {
        dashboard.refresh()
        if let panel = usagePanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 430, height: 410),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Model Usage"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: ModelUsageView(
                model: dashboard,
                close: { [weak self] in self?.usagePanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        usagePanel = panel
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
        panel.delegate = self
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

    func windowWillClose(_ notification: Notification) {
        guard let window = notification.object as? NSWindow else { return }
        if window == modelRoutingPanel {
            modelRoutingPanel = nil
            modelPickers = [:]
            reasoningPickers = [:]
            modelOptions = []
        } else if window == usagePanel {
            usagePanel = nil
        } else if window == logPanel {
            logPanel = nil
        }
    }

    private func revealLogFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("runtime"))
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
