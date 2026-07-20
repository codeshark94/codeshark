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

struct DashboardQueuedTask: Decodable, Identifiable {
    let id: String
    let project: String
    let createdAt: Int

    enum CodingKeys: String, CodingKey {
        case id, project
        case createdAt = "created_at"
    }
}

struct DashboardDelivery: Decodable, Identifiable {
    let taskID: String
    let project: String
    let phase: String
    let deliveryState: String
    let artifacts: [String]
    let artifactPaths: [String]
    let updatedAt: Int

    var id: String { taskID }

    enum CodingKeys: String, CodingKey {
        case project, phase, artifacts
        case taskID = "task_id"
        case deliveryState = "delivery_state"
        case artifactPaths = "artifact_paths"
        case updatedAt = "updated_at"
    }
}

struct DashboardFailedDelivery: Decodable, Identifiable {
    let id: String
    let attempts: Int
    let lastError: String
    let updatedAt: Int

    enum CodingKeys: String, CodingKey {
        case id, attempts
        case lastError = "last_error"
        case updatedAt = "updated_at"
    }
}

struct DashboardProject: Decodable, Identifiable {
    let project: String
    let activeTaskCount: Int
    let queuedTaskCount: Int
    let deliveryCount: Int
    let artifactCount: Int
    let updatedAt: Int

    var id: String { project }

    enum CodingKeys: String, CodingKey {
        case project
        case activeTaskCount = "active_task_count"
        case queuedTaskCount = "queued_task_count"
        case deliveryCount = "delivery_count"
        case artifactCount = "artifact_count"
        case updatedAt = "updated_at"
    }
}

struct DashboardModelAssignment: Decodable, Identifiable {
    let model: String
    let reasoningEffort: String
    let role: String
    let recentTotalTokens: Int?
    let recentMeasuredTurns: Int?
    let recentRuns: Int?

    var id: String { "\(model)-\(reasoningEffort)-\(role)" }

    enum CodingKeys: String, CodingKey {
        case model, role
        case reasoningEffort = "reasoning_effort"
        case recentTotalTokens = "recent_total_tokens"
        case recentMeasuredTurns = "recent_measured_turns"
        case recentRuns = "recent_runs"
    }
}

struct DashboardSecurityGroup: Decodable, Identifiable {
    let chatID: Int
    let title: String
    let enabledAt: Int

    var id: String { String(chatID) }

    enum CodingKeys: String, CodingKey {
        case title
        case chatID = "chat_id"
        case enabledAt = "enabled_at"
    }
}

struct DashboardSecurity: Decodable {
    let sandbox: String
    let networkAccess: Bool
    let adminFullAccess: Bool
    let adminAutoApproveActions: Bool
    let adminMcpEnabled: Bool
    let adminDelegatedWriteAccess: Bool
    let groupNetworkAccess: Bool
    let groupWorkspaceWrite: Bool
    let telegram: String
    let groups: [DashboardSecurityGroup]

    enum CodingKeys: String, CodingKey {
        case sandbox, telegram, groups
        case networkAccess = "network_access"
        case adminFullAccess = "admin_full_access"
        case adminAutoApproveActions = "admin_auto_approve_actions"
        case adminMcpEnabled = "admin_mcp_enabled"
        case adminDelegatedWriteAccess = "admin_delegated_write_access"
        case groupNetworkAccess = "group_network_access"
        case groupWorkspaceWrite = "group_workspace_write"
    }

    init(
        sandbox: String,
        networkAccess: Bool,
        adminFullAccess: Bool,
        adminAutoApproveActions: Bool,
        adminMcpEnabled: Bool,
        adminDelegatedWriteAccess: Bool,
        groupNetworkAccess: Bool,
        groupWorkspaceWrite: Bool,
        telegram: String,
        groups: [DashboardSecurityGroup]
    ) {
        self.sandbox = sandbox
        self.networkAccess = networkAccess
        self.adminFullAccess = adminFullAccess
        self.adminAutoApproveActions = adminAutoApproveActions
        self.adminMcpEnabled = adminMcpEnabled
        self.adminDelegatedWriteAccess = adminDelegatedWriteAccess
        self.groupNetworkAccess = groupNetworkAccess
        self.groupWorkspaceWrite = groupWorkspaceWrite
        self.telegram = telegram
        self.groups = groups
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sandbox = try container.decodeIfPresent(String.self, forKey: .sandbox) ?? "workspace-write"
        networkAccess = try container.decodeIfPresent(Bool.self, forKey: .networkAccess) ?? false
        adminFullAccess = try container.decodeIfPresent(Bool.self, forKey: .adminFullAccess) ?? false
        adminAutoApproveActions = try container.decodeIfPresent(Bool.self, forKey: .adminAutoApproveActions) ?? adminFullAccess
        adminMcpEnabled = try container.decodeIfPresent(Bool.self, forKey: .adminMcpEnabled) ?? true
        adminDelegatedWriteAccess = try container.decodeIfPresent(Bool.self, forKey: .adminDelegatedWriteAccess) ?? true
        groupNetworkAccess = try container.decodeIfPresent(Bool.self, forKey: .groupNetworkAccess) ?? true
        groupWorkspaceWrite = try container.decodeIfPresent(Bool.self, forKey: .groupWorkspaceWrite) ?? true
        telegram = try container.decodeIfPresent(String.self, forKey: .telegram) ?? "Keychain credential"
        groups = try container.decodeIfPresent([DashboardSecurityGroup].self, forKey: .groups) ?? []
    }
}

struct DashboardOrchestrationTier: Decodable {
    let usesPreflight: Bool
    let usesResearch: Bool
    let usesValidator: Bool
    let feedbackIterations: Int
    let usesFinalizer: Bool

    enum CodingKeys: String, CodingKey {
        case usesPreflight = "uses_preflight"
        case usesResearch = "uses_research"
        case usesValidator = "uses_validator"
        case feedbackIterations = "feedback_iterations"
        case usesFinalizer = "uses_finalizer"
    }

    init(
        usesPreflight: Bool = false,
        usesResearch: Bool = false,
        usesValidator: Bool = false,
        feedbackIterations: Int = 0,
        usesFinalizer: Bool = false
    ) {
        self.usesPreflight = usesPreflight
        self.usesResearch = usesResearch
        self.usesValidator = usesValidator
        self.feedbackIterations = feedbackIterations
        self.usesFinalizer = usesFinalizer
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        usesPreflight = try container.decodeIfPresent(Bool.self, forKey: .usesPreflight) ?? false
        usesResearch = try container.decodeIfPresent(Bool.self, forKey: .usesResearch) ?? false
        usesValidator = try container.decodeIfPresent(Bool.self, forKey: .usesValidator) ?? false
        feedbackIterations = try container.decodeIfPresent(Int.self, forKey: .feedbackIterations) ?? 0
        usesFinalizer = try container.decodeIfPresent(Bool.self, forKey: .usesFinalizer) ?? false
    }
}

struct DashboardOrchestration: Decodable {
    let quick: DashboardOrchestrationTier
    let routine: DashboardOrchestrationTier
    let standard: DashboardOrchestrationTier
    let deep: DashboardOrchestrationTier

    let highAssurance: DashboardOrchestrationTier

    enum CodingKeys: String, CodingKey {
        case quick, routine, standard, deep
        case highAssurance = "high_assurance"
    }

    init(
        quick: DashboardOrchestrationTier = DashboardOrchestrationTier(),
        routine: DashboardOrchestrationTier = DashboardOrchestrationTier(),
        standard: DashboardOrchestrationTier = DashboardOrchestrationTier(
            usesValidator: true,
            usesFinalizer: true
        ),
        deep: DashboardOrchestrationTier = DashboardOrchestrationTier(
            usesPreflight: true,
            usesValidator: true,
            feedbackIterations: 1,
            usesFinalizer: true
        ),
        highAssurance: DashboardOrchestrationTier = DashboardOrchestrationTier(
            usesPreflight: true,
            usesResearch: true,
            usesValidator: true,
            feedbackIterations: 2,
            usesFinalizer: true
        )
    ) {
        self.quick = quick
        self.routine = routine
        self.standard = standard
        self.deep = deep
        self.highAssurance = highAssurance
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        quick = try container.decodeIfPresent(DashboardOrchestrationTier.self, forKey: .quick)
            ?? DashboardOrchestrationTier()
        routine = try container.decodeIfPresent(DashboardOrchestrationTier.self, forKey: .routine)
            ?? DashboardOrchestrationTier()
        standard = try container.decodeIfPresent(DashboardOrchestrationTier.self, forKey: .standard)
            ?? DashboardOrchestrationTier(usesValidator: true, usesFinalizer: true)
        deep = try container.decodeIfPresent(DashboardOrchestrationTier.self, forKey: .deep)
            ?? DashboardOrchestrationTier(
                usesPreflight: true,
                usesValidator: true,
                feedbackIterations: 1,
                usesFinalizer: true
            )
        highAssurance = try container.decodeIfPresent(DashboardOrchestrationTier.self, forKey: .highAssurance)
            ?? DashboardOrchestrationTier(
                usesPreflight: true,
                usesResearch: true,
                usesValidator: true,
                feedbackIterations: 2,
                usesFinalizer: true
            )
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
    let measuredRuns: Int?
    let inputTokens: Int?
    let cachedInputTokens: Int?
    let cacheWriteInputTokens: Int?
    let outputTokens: Int?
    let reasoningOutputTokens: Int?
    let totalTokens: Int?

    var id: String { "\(model)-\(reasoningEffort)-\(phase)" }

    enum CodingKeys: String, CodingKey {
        case model, phase, runs, completed
        case reasoningEffort = "reasoning_effort"
        case elapsedSeconds = "elapsed_seconds"
        case measuredRuns = "measured_runs"
        case inputTokens = "input_tokens"
        case cachedInputTokens = "cached_input_tokens"
        case cacheWriteInputTokens = "cache_write_input_tokens"
        case outputTokens = "output_tokens"
        case reasoningOutputTokens = "reasoning_output_tokens"
        case totalTokens = "total_tokens"
    }
}

struct DashboardProjectUsage: Decodable, Identifiable {
    let project: String
    let model: String
    let reasoningEffort: String
    let runs: Int
    let measuredRuns: Int?
    let inputTokens: Int?
    let cachedInputTokens: Int?
    let cacheWriteInputTokens: Int?
    let outputTokens: Int?
    let reasoningOutputTokens: Int?
    let totalTokens: Int?

    var id: String { "\(project)-\(model)-\(reasoningEffort)" }

    enum CodingKeys: String, CodingKey {
        case project, model, runs
        case reasoningEffort = "reasoning_effort"
        case measuredRuns = "measured_runs"
        case inputTokens = "input_tokens"
        case cachedInputTokens = "cached_input_tokens"
        case cacheWriteInputTokens = "cache_write_input_tokens"
        case outputTokens = "output_tokens"
        case reasoningOutputTokens = "reasoning_output_tokens"
        case totalTokens = "total_tokens"
    }
}

struct DashboardQuotaWindow: Decodable {
    let usedPercent: Int
    let resetsAt: Int?
    let windowDurationMins: Int?

    enum CodingKeys: String, CodingKey {
        case usedPercent = "used_percent"
        case resetsAt = "resets_at"
        case windowDurationMins = "window_duration_mins"
    }
}

struct DashboardUsageBucket: Decodable, Identifiable {
    let limitID: String
    let limitName: String?
    let primary: DashboardQuotaWindow?
    let secondary: DashboardQuotaWindow?

    var id: String { limitID }

    enum CodingKeys: String, CodingKey {
        case limitID = "limit_id"
        case limitName = "limit_name"
        case primary, secondary
    }
}

struct DashboardAccountUsage: Decodable {
    let observedAt: Int
    let buckets: [DashboardUsageBucket]

    enum CodingKeys: String, CodingKey {
        case observedAt = "observed_at"
        case buckets
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
    let queuedTasks: [DashboardQueuedTask]
    let recentArtifacts: [String]
    let recentDeliveries: [DashboardDelivery]
    let failedDeliveries: [DashboardFailedDelivery]
    let projects: [DashboardProject]
    let lastFailure: DashboardFailure?
    let activityLog: [DashboardActivityLog]
    let modelUsage5h: [DashboardModelUsage]
    let modelUsage7d: [DashboardModelUsage]
    let projectUsage5h: [DashboardProjectUsage]
    let projectUsage7d: [DashboardProjectUsage]
    let accountUsage: DashboardAccountUsage?
    let orchestration: DashboardOrchestration?
    let security: DashboardSecurity?

    static let empty = DashboardSnapshot(
        state: "starting",
        activeTaskCount: 0,
        queueCount: 0,
        workspacePath: "",
        modelAssignments: [],
        activeTasks: [],
        queuedTasks: [],
        recentArtifacts: [],
        recentDeliveries: [],
        failedDeliveries: [],
        projects: [],
        lastFailure: nil,
        activityLog: [],
        modelUsage5h: [],
        modelUsage7d: [],
        projectUsage5h: [],
        projectUsage7d: [],
        accountUsage: nil,
        orchestration: nil,
        security: nil
    )

    enum CodingKeys: String, CodingKey {
        case state
        case activeTaskCount = "active_task_count"
        case queueCount = "queue_count"
        case workspacePath = "workspace_path"
        case modelAssignments = "model_assignments"
        case activeTasks = "active_tasks"
        case queuedTasks = "queued_tasks"
        case recentArtifacts = "recent_artifacts"
        case recentDeliveries = "recent_deliveries"
        case failedDeliveries = "failed_deliveries"
        case projects
        case lastFailure = "last_failure"
        case activityLog = "activity_log"
        case modelUsage5h = "model_usage_5h"
        case modelUsage7d = "model_usage_7d"
        case projectUsage5h = "project_usage_5h"
        case projectUsage7d = "project_usage_7d"
        case accountUsage = "account_usage"
        case orchestration
        case security
    }

    init(
        state: String,
        activeTaskCount: Int,
        queueCount: Int,
        workspacePath: String,
        modelAssignments: [DashboardModelAssignment],
        activeTasks: [DashboardTask],
        queuedTasks: [DashboardQueuedTask],
        recentArtifacts: [String],
        recentDeliveries: [DashboardDelivery],
        failedDeliveries: [DashboardFailedDelivery],
        projects: [DashboardProject],
        lastFailure: DashboardFailure?,
        activityLog: [DashboardActivityLog],
        modelUsage5h: [DashboardModelUsage],
        modelUsage7d: [DashboardModelUsage],
        projectUsage5h: [DashboardProjectUsage],
        projectUsage7d: [DashboardProjectUsage],
        accountUsage: DashboardAccountUsage?,
        orchestration: DashboardOrchestration?,
        security: DashboardSecurity?
    ) {
        self.state = state
        self.activeTaskCount = activeTaskCount
        self.queueCount = queueCount
        self.workspacePath = workspacePath
        self.modelAssignments = modelAssignments
        self.activeTasks = activeTasks
        self.queuedTasks = queuedTasks
        self.recentArtifacts = recentArtifacts
        self.recentDeliveries = recentDeliveries
        self.failedDeliveries = failedDeliveries
        self.projects = projects
        self.lastFailure = lastFailure
        self.activityLog = activityLog
        self.modelUsage5h = modelUsage5h
        self.modelUsage7d = modelUsage7d
        self.projectUsage5h = projectUsage5h
        self.projectUsage7d = projectUsage7d
        self.accountUsage = accountUsage
        self.orchestration = orchestration
        self.security = security
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "starting"
        activeTaskCount = try container.decodeIfPresent(Int.self, forKey: .activeTaskCount) ?? 0
        queueCount = try container.decodeIfPresent(Int.self, forKey: .queueCount) ?? 0
        workspacePath = try container.decodeIfPresent(String.self, forKey: .workspacePath) ?? ""
        modelAssignments = try container.decodeIfPresent([DashboardModelAssignment].self, forKey: .modelAssignments) ?? []
        activeTasks = try container.decodeIfPresent([DashboardTask].self, forKey: .activeTasks) ?? []
        queuedTasks = try container.decodeIfPresent([DashboardQueuedTask].self, forKey: .queuedTasks) ?? []
        recentArtifacts = try container.decodeIfPresent([String].self, forKey: .recentArtifacts) ?? []
        recentDeliveries = try container.decodeIfPresent([DashboardDelivery].self, forKey: .recentDeliveries) ?? []
        failedDeliveries = try container.decodeIfPresent([DashboardFailedDelivery].self, forKey: .failedDeliveries) ?? []
        projects = try container.decodeIfPresent([DashboardProject].self, forKey: .projects) ?? []
        lastFailure = try container.decodeIfPresent(DashboardFailure.self, forKey: .lastFailure)
        activityLog = try container.decodeIfPresent([DashboardActivityLog].self, forKey: .activityLog) ?? []
        modelUsage5h = try container.decodeIfPresent([DashboardModelUsage].self, forKey: .modelUsage5h) ?? []
        modelUsage7d = try container.decodeIfPresent([DashboardModelUsage].self, forKey: .modelUsage7d) ?? []
        projectUsage5h = try container.decodeIfPresent([DashboardProjectUsage].self, forKey: .projectUsage5h) ?? []
        projectUsage7d = try container.decodeIfPresent([DashboardProjectUsage].self, forKey: .projectUsage7d) ?? []
        accountUsage = try container.decodeIfPresent(DashboardAccountUsage.self, forKey: .accountUsage)
        orchestration = try container.decodeIfPresent(DashboardOrchestration.self, forKey: .orchestration)
        security = try container.decodeIfPresent(DashboardSecurity.self, forKey: .security)
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

private struct LocalConsoleMessage: Decodable, Identifiable {
    let id: Int
    let taskID: String?
    let role: String
    let text: String
    let attachments: [String]
    let createdAt: Int

    enum CodingKeys: String, CodingKey {
        case id, role, text, attachments
        case taskID = "task_id"
        case createdAt = "created_at"
    }
}

private struct LocalConsoleHistory: Decodable {
    let messages: [LocalConsoleMessage]
}

private struct LocalConsoleSubmission: Decodable {
    let taskID: String

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
    }
}

private final class LocalConsoleModel: ObservableObject {
    typealias Command = ([String]) -> (status: Int32, output: String)

    @Published private(set) var messages: [LocalConsoleMessage] = []
    @Published var draft = ""
    @Published var attachments: [String] = []
    @Published private(set) var status = ""
    @Published private(set) var sending = false

    private let command: Command
    private var refreshTimer: Timer?

    init(command: @escaping Command) {
        self.command = command
        refresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    deinit {
        refreshTimer?.invalidate()
    }

    func refresh() {
        let command = command
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let result = command(["local-history", "--limit", "120"])
            guard result.status == 0,
                  let payload = result.output.data(using: .utf8),
                  let history = try? JSONDecoder().decode(LocalConsoleHistory.self, from: payload)
            else {
                return
            }
            DispatchQueue.main.async {
                self?.messages = history.messages
            }
        }
    }

    func addAttachments(_ urls: [URL]) {
        for url in urls where !attachments.contains(url.path) {
            attachments.append(url.path)
        }
    }

    func removeAttachment(_ path: String) {
        attachments.removeAll { $0 == path }
    }

    func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let files = attachments
        guard !sending, !text.isEmpty || !files.isEmpty else { return }
        sending = true
        status = "Sending…"
        draft = ""
        attachments = []
        let command = command
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var arguments = ["local-send", "--text", text]
            for file in files {
                arguments += ["--file", file]
            }
            let result = command(arguments)
            let taskID = result.output.data(using: .utf8)
                .flatMap { try? JSONDecoder().decode(LocalConsoleSubmission.self, from: $0) }
                .map(\.taskID)
            DispatchQueue.main.async {
                guard let self else { return }
                self.sending = false
                self.status = result.status == 0
                    ? "Queued\(taskID.map { " · \($0)" } ?? "")"
                    : (result.output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        ? "Could not queue the task."
                        : result.output.trimmingCharacters(in: .whitespacesAndNewlines))
                self.refresh()
            }
        }
    }
}

private struct LocalConsoleView: View {
    @ObservedObject var model: LocalConsoleModel
    @ObservedObject var dashboard: DashboardModel
    let chooseFiles: () -> Void
    let revealArtifacts: ([String]) -> Void
    let revealWorkspace: () -> Void
    let close: () -> Void

    private func bubbleColor(_ role: String) -> Color {
        role == "user" ? .blue.opacity(0.80) : role == "system" ? .secondary.opacity(0.10) : .secondary.opacity(0.16)
    }

    private func foreground(_ role: String) -> Color {
        role == "user" ? .white : .primary
    }

    private var isWorking: Bool { dashboard.snapshot.state == "working" }

    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor).ignoresSafeArea()
            VStack(spacing: 14) {
                HStack(spacing: 11) {
                    Image(systemName: "chevron.left.forwardslash.chevron.right")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 34, height: 34)
                        .background(.blue.gradient, in: RoundedRectangle(cornerRadius: 10))
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Codeshark").font(.title3.weight(.semibold))
                        HStack(spacing: 5) {
                            Circle().fill(isWorking ? .blue : .green).frame(width: 6, height: 6)
                            Text(isWorking ? "Working locally" : "Ready · local session")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button(action: revealWorkspace) { Image(systemName: "folder") }
                        .buttonStyle(.bordered).help("Reveal workspace")
                    Button("Close", action: close).buttonStyle(.bordered)
                }
                .padding(.horizontal, 2)

                Divider()

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        if model.messages.isEmpty {
                            VStack(spacing: 12) {
                                Image(systemName: "sparkles").font(.system(size: 28, weight: .medium)).foregroundStyle(.blue)
                                Text("Start a direct Codeshark task").font(.headline)
                                Text("Use the same workspace, models, and output delivery without Telegram.")
                                    .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 360)
                            }
                            .frame(maxWidth: .infinity, minHeight: 290)
                        } else {
                            ForEach(model.messages) { message in
                                if message.role == "system" {
                                    Text(message.text)
                                        .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                                        .padding(.horizontal, 12).padding(.vertical, 6)
                                        .background(bubbleColor(message.role), in: Capsule())
                                        .frame(maxWidth: .infinity)
                                } else {
                                    HStack(alignment: .bottom, spacing: 8) {
                                        if message.role == "user" { Spacer(minLength: 70) }
                                        VStack(alignment: .leading, spacing: 7) {
                                            HStack(spacing: 6) {
                                                Image(systemName: message.role == "user" ? "person.fill" : "bolt.fill")
                                                Text(message.role == "user" ? "You" : "Codeshark")
                                                Text(timeAgoText(message.createdAt)).font(.caption2).opacity(0.78)
                                            }
                                            .font(.caption.weight(.semibold)).foregroundStyle(foreground(message.role).opacity(0.82))
                                            if !message.text.isEmpty {
                                                Text(message.text).font(.body).textSelection(.enabled)
                                                    .foregroundStyle(foreground(message.role)).frame(maxWidth: .infinity, alignment: .leading)
                                            }
                                            ForEach(message.attachments, id: \.self) { path in
                                                Button {
                                                    revealArtifacts([path])
                                                } label: {
                                                    HStack(spacing: 6) {
                                                        Image(systemName: "doc.fill")
                                                        Text(URL(fileURLWithPath: path).lastPathComponent).lineLimit(1)
                                                        Spacer(minLength: 4)
                                                        Image(systemName: "arrow.up.forward.app")
                                                    }
                                                    .font(.caption.weight(.medium)).foregroundStyle(foreground(message.role))
                                                    .padding(.horizontal, 9).padding(.vertical, 7)
                                                    .background(.black.opacity(message.role == "user" ? 0.16 : 0.07), in: RoundedRectangle(cornerRadius: 7))
                                                }
                                                .buttonStyle(.plain)
                                            }
                                        }
                                        .padding(11).frame(maxWidth: 470, alignment: .leading)
                                        .background(bubbleColor(message.role), in: RoundedRectangle(cornerRadius: 14))
                                        if message.role != "user" { Spacer(minLength: 70) }
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 2).padding(.vertical, 2)
                }
                .frame(minHeight: 310)

                VStack(spacing: 8) {
                    if !model.attachments.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(model.attachments, id: \.self) { path in
                                    HStack(spacing: 5) {
                                        Image(systemName: "paperclip")
                                        Text(URL(fileURLWithPath: path).lastPathComponent).lineLimit(1)
                                        Button { model.removeAttachment(path) } label: { Image(systemName: "xmark.circle.fill") }
                                            .buttonStyle(.plain)
                                    }
                                    .font(.caption).padding(.horizontal, 9).padding(.vertical, 6)
                                    .background(.quaternary, in: Capsule())
                                }
                            }
                        }
                    }
                    HStack(alignment: .bottom, spacing: 9) {
                        Button(action: chooseFiles) { Image(systemName: "paperclip").frame(width: 20, height: 20) }
                            .buttonStyle(.bordered)
                        TextEditor(text: $model.draft).font(.body).frame(minHeight: 42, maxHeight: 78)
                        Button { model.send() } label: {
                            Image(systemName: model.sending ? "hourglass" : "arrow.up")
                                .font(.system(size: 13, weight: .bold)).frame(width: 30, height: 30)
                        }
                        .buttonStyle(.borderedProminent).clipShape(Circle())
                        .disabled(model.sending || (model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && model.attachments.isEmpty))
                    }
                    if !model.status.isEmpty {
                        Text(model.status).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(10).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            }
        }
        .padding(16)
        .frame(minWidth: 640, minHeight: 600, alignment: .topLeading)
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

private func tokenText(_ tokens: Int) -> String {
    if tokens >= 1_000_000 {
        return String(format: "%.1fM tokens", Double(tokens) / 1_000_000)
    }
    if tokens >= 1_000 {
        return String(format: "%.1fK tokens", Double(tokens) / 1_000)
    }
    return "\(tokens) tokens"
}

private final class StatusMenuRow: NSView {
    private let dotColor: NSColor

    init(title: String, color: NSColor) {
        dotColor = color
        super.init(frame: NSRect(x: 0, y: 0, width: 320, height: 28))

        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 14)
        label.textColor = .secondaryLabelColor
        label.frame = NSRect(x: 34, y: 5, width: 272, height: 18)
        addSubview(label)
    }

    required init?(coder: NSCoder) {
        nil
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        dotColor.setFill()
        NSBezierPath(ovalIn: NSRect(x: 16, y: 8, width: 12, height: 12)).fill()
    }

    override func mouseDown(with event: NSEvent) {}
}

private func quotaWindowText(_ window: DashboardQuotaWindow) -> String {
    let duration: String
    if let minutes = window.windowDurationMins {
        duration = minutes < 24 * 60 ? "\(minutes / 60)h window" : "\(minutes / (24 * 60))d window"
    } else {
        duration = "rolling window"
    }
    guard let reset = window.resetsAt else { return duration }
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, HH:mm"
    return "\(duration) · resets \(formatter.string(from: Date(timeIntervalSince1970: TimeInterval(reset))))"
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

private func deliveryStateTitle(_ state: String) -> String {
    switch state {
    case "delivered":
        return "Delivered"
    case "failed":
        return "Needs follow-up"
    case "required":
        return "Awaiting delivery"
    case "not-requested":
        return "No file requested"
    default:
        return state.replacingOccurrences(of: "-", with: " ").capitalized
    }
}

private struct OperationsFooter: View {
    let primaryTitle: String
    let primaryAction: () -> Void
    let close: () -> Void

    var body: some View {
        HStack {
            Button(primaryTitle, action: primaryAction)
                .buttonStyle(.bordered)
            Spacer()
            Button("Close", action: close)
                .buttonStyle(.bordered)
        }
    }
}

struct TaskQueueView: View {
    @ObservedObject var model: DashboardModel
    let showLogs: () -> Void
    let close: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }
    private var queueCount: Int { max(snapshot.queueCount, snapshot.queuedTasks.count) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Tasks")
                    .font(.system(size: 16, weight: .semibold))
                Text("\(snapshot.activeTasks.count) active · \(queueCount) queued")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if !snapshot.activeTasks.isEmpty {
                        Text("ACTIVE")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        ForEach(snapshot.activeTasks) { task in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(task.project)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    Text(elapsedText(task.elapsedSeconds))
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                                Text("\(task.phase) · \(compactModelName(task.model)) · \(task.reasoningEffort)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }

                    if !snapshot.queuedTasks.isEmpty {
                        Text("QUEUE")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .padding(.top, snapshot.activeTasks.isEmpty ? 0 : 4)
                        ForEach(snapshot.queuedTasks) { task in
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(task.project)
                                        .font(.subheadline.weight(.medium))
                                        .lineLimit(1)
                                    Text("Queued \(timeAgoText(task.createdAt)) · \(task.id)")
                                        .font(.caption.monospaced())
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "clock")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    } else if snapshot.queueCount > 0 {
                        Label("\(snapshot.queueCount) queued work item\(snapshot.queueCount == 1 ? "" : "s")", systemImage: "clock")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    }

                    if snapshot.activeTasks.isEmpty && snapshot.queuedTasks.isEmpty && snapshot.queueCount == 0 {
                        Label("No active or queued work", systemImage: "checkmark.circle")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    }
                }
            }

            Divider()
            OperationsFooter(primaryTitle: "Logs", primaryAction: showLogs, close: close)
        }
        .padding(16)
        .frame(width: 460, height: 430, alignment: .topLeading)
    }
}

struct DeliveryCenterView: View {
    @ObservedObject var model: DashboardModel
    let showLogs: () -> Void
    let revealArtifacts: ([String]) -> Void
    let close: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Delivery")
                    .font(.system(size: 16, weight: .semibold))
                Text("Recent file outcomes and Telegram delivery failures.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if !snapshot.failedDeliveries.isEmpty {
                        Text("NEEDS ATTENTION")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        ForEach(snapshot.failedDeliveries) { delivery in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Label("Telegram delivery \(delivery.id)", systemImage: "exclamationmark.triangle.fill")
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.red)
                                    Spacer()
                                    Text("\(delivery.attempts)x")
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                                Text(delivery.lastError)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }

                    if !snapshot.recentDeliveries.isEmpty {
                        Text("RECENT")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .padding(.top, snapshot.failedDeliveries.isEmpty ? 0 : 4)
                        ForEach(snapshot.recentDeliveries) { delivery in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(delivery.project)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    Text(deliveryStateTitle(delivery.deliveryState))
                                        .font(.caption.weight(.medium))
                                        .foregroundStyle(delivery.deliveryState == "failed" ? .red : .secondary)
                                }
                                Text(delivery.artifacts.isEmpty ? "No attached file" : delivery.artifacts.joined(separator: " · "))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                                Text("\(delivery.phase) · \(timeAgoText(delivery.updatedAt))")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                if !delivery.artifactPaths.isEmpty {
                                    Button("Reveal", action: { revealArtifacts(delivery.artifactPaths) })
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                }
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    } else if !snapshot.recentArtifacts.isEmpty {
                        Text("RECENT FILES")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .padding(.top, snapshot.failedDeliveries.isEmpty ? 0 : 4)
                        ForEach(snapshot.recentArtifacts, id: \.self) { artifact in
                            Label(artifact, systemImage: "doc")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .padding(.vertical, 2)
                        }
                    }

                    if snapshot.failedDeliveries.isEmpty && snapshot.recentDeliveries.isEmpty && snapshot.recentArtifacts.isEmpty {
                        Label("No delivery activity yet", systemImage: "tray")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    }
                }
            }

            Divider()
            OperationsFooter(primaryTitle: "Logs", primaryAction: showLogs, close: close)
        }
        .padding(16)
        .frame(width: 500, height: 470, alignment: .topLeading)
    }
}

struct ProjectOverviewView: View {
    @ObservedObject var model: DashboardModel
    let revealWorkspace: () -> Void
    let close: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Projects")
                    .font(.system(size: 16, weight: .semibold))
                Text("Local overview only. Telegram project sessions remain isolated by conversation.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if snapshot.projects.isEmpty {
                        Label("No project activity yet", systemImage: "folder")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    } else {
                        ForEach(snapshot.projects) { project in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(project.project)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    if project.updatedAt > 0 {
                                        Text(timeAgoText(project.updatedAt))
                                            .font(.caption.monospacedDigit())
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Text("\(project.activeTaskCount) active · \(project.queuedTaskCount) queued · \(project.deliveryCount) deliveries · \(project.artifactCount) files")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
            }

            Divider()
            OperationsFooter(primaryTitle: "Reveal Workspace", primaryAction: revealWorkspace, close: close)
        }
        .padding(16)
        .frame(width: 500, height: 420, alignment: .topLeading)
    }
}

struct AttentionView: View {
    @ObservedObject var model: DashboardModel
    let showLogs: () -> Void
    let close: () -> Void

    private var snapshot: DashboardSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Attention")
                    .font(.system(size: 16, weight: .semibold))
                Text("Failures that may need a retry or local inspection.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            if snapshot.lastFailure == nil && snapshot.failedDeliveries.isEmpty {
                Spacer()
                Label("All clear", systemImage: "checkmark.circle.fill")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.green)
                Text("No task or Telegram delivery failure is awaiting attention.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        if let failure = snapshot.lastFailure {
                            VStack(alignment: .leading, spacing: 4) {
                                Label("Task \(failure.taskID)", systemImage: "xmark.circle.fill")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.red)
                                Text(failure.message)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                        ForEach(snapshot.failedDeliveries) { delivery in
                            VStack(alignment: .leading, spacing: 4) {
                                Label("Delivery \(delivery.id) · \(delivery.attempts)x", systemImage: "exclamationmark.triangle.fill")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.orange)
                                Text(delivery.lastError)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
            }

            Divider()
            OperationsFooter(primaryTitle: "Logs", primaryAction: showLogs, close: close)
        }
        .padding(16)
        .frame(width: 460, height: 360, alignment: .topLeading)
    }
}

private struct ModelUsageGroup: Identifiable {
    let model: String
    let reasoningEffort: String
    let runs: Int
    let completed: Int
    let measuredRuns: Int
    let inputTokens: Int
    let cachedInputTokens: Int
    let cacheWriteInputTokens: Int
    let outputTokens: Int
    let reasoningOutputTokens: Int
    let totalTokens: Int

    var id: String { "\(model)-\(reasoningEffort)" }
}

private struct APIModelPrice {
    let input: Double
    let cachedInput: Double
    let cacheWriteInput: Double?
    let output: Double
}

private func apiModelPrice(for model: String) -> APIModelPrice? {
    // Official OpenAI standard API list prices per 1M tokens. GPT-5.6 cache writes cost 1.25× input.
    switch model {
    case "gpt-5.6-sol":
        return APIModelPrice(input: 5.00, cachedInput: 0.50, cacheWriteInput: 6.25, output: 30.00)
    case "gpt-5.6-terra":
        return APIModelPrice(input: 2.50, cachedInput: 0.25, cacheWriteInput: 3.125, output: 15.00)
    case "gpt-5.6-luna":
        return APIModelPrice(input: 1.00, cachedInput: 0.10, cacheWriteInput: 1.25, output: 6.00)
    case "gpt-5.5":
        return APIModelPrice(input: 5.00, cachedInput: 0.50, cacheWriteInput: nil, output: 30.00)
    case "gpt-5.4":
        return APIModelPrice(input: 2.50, cachedInput: 0.25, cacheWriteInput: nil, output: 15.00)
    case "gpt-5.4-mini":
        return APIModelPrice(input: 0.75, cachedInput: 0.075, cacheWriteInput: nil, output: 4.50)
    case "gpt-5.4-nano":
        return APIModelPrice(input: 0.20, cachedInput: 0.02, cacheWriteInput: nil, output: 1.25)
    case "gpt-5.3-codex", "gpt-5.2":
        return APIModelPrice(input: 1.75, cachedInput: 0.175, cacheWriteInput: nil, output: 14.00)
    default:
        return nil
    }
}

private func apiEquivalentCost(
    model: String,
    inputTokens: Int,
    cachedInputTokens: Int,
    cacheWriteInputTokens: Int,
    outputTokens: Int,
    reasoningOutputTokens: Int
) -> Double? {
    guard let price = apiModelPrice(for: model) else { return nil }
    let cached = min(inputTokens, cachedInputTokens)
    let cacheWrites = min(max(0, inputTokens - cached), cacheWriteInputTokens)
    guard cacheWrites == 0 || price.cacheWriteInput != nil else { return nil }
    let uncached = max(0, inputTokens - cached - cacheWrites)
    let output = outputTokens + reasoningOutputTokens
    return Double(uncached) * price.input / 1_000_000
        + Double(cached) * price.cachedInput / 1_000_000
        + Double(cacheWrites) * (price.cacheWriteInput ?? 0) / 1_000_000
        + Double(output) * price.output / 1_000_000
}

private func apiCostText(_ amount: Double) -> String {
    amount >= 1 ? String(format: "$%.2f", amount) : String(format: "$%.4f", amount)
}

private struct ProjectUsageGroup: Identifiable {
    let project: String
    let entries: [DashboardProjectUsage]

    var id: String { project }
    var totalTokens: Int { entries.reduce(0) { $0 + ($1.totalTokens ?? 0) } }
    var measuredRuns: Int { entries.reduce(0) { $0 + ($1.measuredRuns ?? 0) } }
    var runs: Int { entries.reduce(0) { $0 + $1.runs } }
    var estimatedAPICost: Double? {
        let costs = entries.compactMap {
            apiEquivalentCost(
                model: $0.model,
                inputTokens: $0.inputTokens ?? 0,
                cachedInputTokens: $0.cachedInputTokens ?? 0,
                cacheWriteInputTokens: $0.cacheWriteInputTokens ?? 0,
                outputTokens: $0.outputTokens ?? 0,
                reasoningOutputTokens: $0.reasoningOutputTokens ?? 0
            )
        }
        return costs.isEmpty ? nil : costs.reduce(0, +)
    }
}

struct ModelUsageView: View {
    @ObservedObject var model: DashboardModel
    let close: () -> Void
    @State private var period = 0
    @State private var breakdown = 0

    private func routingKey(model: String, reasoningEffort: String) -> String {
        "\(model)-\(reasoningEffort)"
    }

    private var routedModelKeys: Set<String> {
        Set(
            model.snapshot.modelAssignments.map {
                routingKey(model: $0.model, reasoningEffort: $0.reasoningEffort)
            }
        )
    }

    private var entries: [DashboardModelUsage] {
        let source = period == 0 ? model.snapshot.modelUsage5h : model.snapshot.modelUsage7d
        guard !routedModelKeys.isEmpty else { return source }
        return source.filter {
            routedModelKeys.contains(routingKey(model: $0.model, reasoningEffort: $0.reasoningEffort))
        }
    }

    private var projectEntries: [DashboardProjectUsage] {
        period == 0 ? model.snapshot.projectUsage5h : model.snapshot.projectUsage7d
    }

    private var groups: [ModelUsageGroup] {
        let grouped = Dictionary(grouping: entries) {
            "\($0.model)-\($0.reasoningEffort)"
        }
        var routingOrder: [String: Int] = [:]
        for (index, assignment) in model.snapshot.modelAssignments.enumerated() {
            let key = "\(assignment.model)-\(assignment.reasoningEffort)"
            if routingOrder[key] == nil {
                routingOrder[key] = index
            }
        }
        return grouped.values.map { entries in
            ModelUsageGroup(
                model: entries[0].model,
                reasoningEffort: entries[0].reasoningEffort,
                runs: entries.reduce(0) { $0 + $1.runs },
                completed: entries.reduce(0) { $0 + $1.completed },
                measuredRuns: entries.reduce(0) { $0 + ($1.measuredRuns ?? 0) },
                inputTokens: entries.reduce(0) { $0 + ($1.inputTokens ?? 0) },
                cachedInputTokens: entries.reduce(0) { $0 + ($1.cachedInputTokens ?? 0) },
                cacheWriteInputTokens: entries.reduce(0) { $0 + ($1.cacheWriteInputTokens ?? 0) },
                outputTokens: entries.reduce(0) { $0 + ($1.outputTokens ?? 0) },
                reasoningOutputTokens: entries.reduce(0) { $0 + ($1.reasoningOutputTokens ?? 0) },
                totalTokens: entries.reduce(0) { $0 + ($1.totalTokens ?? 0) }
            )
        }
        .sorted {
            let left = routingOrder[$0.id] ?? Int.max
            let right = routingOrder[$1.id] ?? Int.max
            return left == right ? $0.id < $1.id : left < right
        }
    }

    private var totalTokens: Int {
        groups.reduce(0) { $0 + $1.totalTokens }
    }

    private var estimatedAPICost: Double {
        groups.reduce(0) { total, group in
            total + (apiEquivalentCost(
                model: group.model,
                inputTokens: group.inputTokens,
                cachedInputTokens: group.cachedInputTokens,
                cacheWriteInputTokens: group.cacheWriteInputTokens,
                outputTokens: group.outputTokens,
                reasoningOutputTokens: group.reasoningOutputTokens
            ) ?? 0)
        }
    }

    private var projectGroups: [ProjectUsageGroup] {
        Dictionary(grouping: projectEntries, by: \.project)
            .map { ProjectUsageGroup(project: $0.key, entries: $0.value) }
            .sorted { $0.totalTokens == $1.totalTokens ? $0.project < $1.project : $0.totalTokens > $1.totalTokens }
    }

    private var projectTotalTokens: Int {
        projectGroups.reduce(0) { $0 + $1.totalTokens }
    }

    private var projectEstimatedAPICost: Double {
        projectGroups.reduce(0) { $0 + ($1.estimatedAPICost ?? 0) }
    }

    private var displayedTotalTokens: Int {
        breakdown == 0 ? totalTokens : projectTotalTokens
    }

    private var displayedAPICost: Double {
        breakdown == 0 ? estimatedAPICost : projectEstimatedAPICost
    }

    private var unpricedModels: [String] {
        let source = breakdown == 0 ? entries.map(\.model) : projectEntries.map(\.model)
        return Array(Set(source.filter { apiModelPrice(for: $0) == nil })).sorted()
    }

    private var visibleQuotaBuckets: [DashboardUsageBucket] {
        (model.snapshot.accountUsage?.buckets ?? []).filter { bucket in
            !"\(bucket.limitID) \(bucket.limitName ?? "")"
                .localizedCaseInsensitiveContains("spark")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Model Usage")
                    .font(.system(size: 16, weight: .semibold))
                Text("Account quota and model usage.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            if !visibleQuotaBuckets.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("Codex account quota (all sessions)")
                        .font(.subheadline.weight(.semibold))
                    Text("Includes separate Codex work on this ChatGPT account.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(visibleQuotaBuckets) { bucket in
                        if let window = bucket.primary {
                            VStack(alignment: .leading, spacing: 3) {
                                HStack {
                                    Text(bucket.limitName ?? (bucket.limitID == "codex" ? "Codex" : bucket.limitID))
                                        .font(.caption.weight(.medium))
                                    Spacer()
                                    Text("\(window.usedPercent)% used")
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                                ProgressView(value: Double(window.usedPercent), total: 100)
                                Text(quotaWindowText(window))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding(10)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
            } else if model.snapshot.accountUsage == nil {
                Text("Live account quota is loading or temporarily unavailable.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                Picker("Period", selection: $period) {
                    Text("5 hours").tag(0)
                    Text("7 days").tag(1)
                }
                Picker("Breakdown", selection: $breakdown) {
                    Text("Models").tag(0)
                    Text("Projects").tag(1)
                }
            }
            .labelsHidden()
            .pickerStyle(.segmented)

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("TOTAL TOKENS")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(tokenText(displayedTotalTokens))
                        .font(.subheadline.weight(.semibold))
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("API-EQUIVALENT")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(apiCostText(displayedAPICost))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))

            Text("Recorded cache and reasoning output are included in the API-equivalent estimate.")
                .font(.caption2)
                .foregroundStyle(.secondary)

            if !unpricedModels.isEmpty {
                Text("No public standard API rate: \(unpricedModels.joined(separator: ", ")).")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Text(breakdown == 0 ? "Model usage" : "Project estimate")
                .font(.subheadline.weight(.semibold))

            ScrollView {
                if breakdown == 0 {
                    LazyVGrid(
                        columns: [
                            GridItem(.flexible(minimum: 0), spacing: 8),
                            GridItem(.flexible(minimum: 0), spacing: 8),
                        ],
                        alignment: .leading,
                        spacing: 8
                    ) {
                        if groups.isEmpty {
                            Label("No recorded model phases", systemImage: "chart.bar")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(groups) { group in
                                let share = totalTokens > 0
                                    ? Int((Double(group.totalTokens) / Double(totalTokens) * 100).rounded())
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
                                    Text("\(tokenText(group.totalTokens)) · exact data \(group.measuredRuns)/\(group.runs) turns · \(group.completed) completed")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                        .frame(maxWidth: .infinity, minHeight: 30, maxHeight: 30, alignment: .topLeading)
                                    ProgressView(value: totalTokens > 0 ? Double(group.totalTokens) / Double(totalTokens) : 0)
                                }
                                .padding(9)
                                .frame(maxWidth: .infinity, minHeight: 86, maxHeight: 86, alignment: .topLeading)
                                .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                            }
                        }
                    }
                } else if projectGroups.isEmpty {
                    Label("No project usage yet", systemImage: "folder")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(projectGroups) { group in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(group.project)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    Text(group.estimatedAPICost.map(apiCostText) ?? "No public rate")
                                        .font(.subheadline.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(group.estimatedAPICost == nil ? .secondary : .primary)
                                }
                                Text("\(tokenText(group.totalTokens)) · exact data \(group.measuredRuns)/\(group.runs) turns · \(group.entries.count) model configurations")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                ProgressView(value: totalTokens > 0 ? Double(group.totalTokens) / Double(totalTokens) : 0)
                            }
                            .padding(10)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
            }
            .frame(maxHeight: 274)

            Divider()

            HStack {
                Spacer()
                Button("Close", action: close)
                    .buttonStyle(.bordered)
                    .frame(minWidth: 84, minHeight: 30)
            }
            .frame(maxWidth: .infinity, minHeight: 30, alignment: .trailing)
            .padding(.bottom, 12)

        }
        .padding(16)
        .frame(minWidth: 560, idealWidth: 580, maxWidth: .infinity,
               minHeight: 712, idealHeight: 732, maxHeight: .infinity,
               alignment: .top)
    }
}

final class CodesharkStatusBar: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate {
    private let projectRoot: String
    private let iconPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: 26)
    private let menu = NSMenu()
    private let dashboard: DashboardModel
    private var logPanel: NSPanel?
    private var usagePanel: NSPanel?
    private var taskPanel: NSPanel?
    private var deliveryPanel: NSPanel?
    private var projectsPanel: NSPanel?
    private var attentionPanel: NSPanel?
    private var modelRoutingPanel: NSPanel?
    private var orchestrationPanel: NSPanel?
    private var settingsPanel: NSPanel?
    private var securityPanel: NSPanel?
    private var localConsolePanel: NSPanel?
    private var localConsoleModel: LocalConsoleModel?
    private var securityNetworkAccess: NSButton?
    private var securityAdminFullAccess: NSButton?
    private var securityAdminAutoApprove: NSButton?
    private var securityAdminMcp: NSButton?
    private var securityAdminDelegatedWrite: NSButton?
    private var securityGroupNetwork: NSButton?
    private var securityGroupWorkspaceWrite: NSButton?
    private var modelPickers: [String: NSPopUpButton] = [:]
    private var reasoningPickers: [String: NSPopUpButton] = [:]
    private var orchestrationPreflight: [String: NSButton] = [:]
    private var orchestrationResearch: [String: NSButton] = [:]
    private var orchestrationValidation: [String: NSButton] = [:]
    private var orchestrationFeedback: [String: NSPopUpButton] = [:]
    private var orchestrationFinalization: [String: NSButton] = [:]
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
                image.size = NSSize(width: 21, height: 18)
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
            action: nil,
            keyEquivalent: ""
        )
        status.view = StatusMenuRow(
            title: "Codeshark is \(statusTitle(for: snapshot).lowercased())",
            color: statusMenuColor(for: snapshot)
        )
        menu.addItem(status)
        menu.addItem(.separator())

        if let failure = snapshot.lastFailure {
            menu.addItem(.separator())
            addSection("Last Task", to: menu)
            addSecondary(failure.message, to: menu)
        }

        menu.addItem(actionItem("Open Codeshark", action: #selector(openLocalConsole(_:))))
        menu.addItem(.separator())
        let taskTitle = snapshot.queueCount > 0 || snapshot.activeTaskCount > 0
            ? "Tasks · \(snapshot.activeTaskCount) active · \(snapshot.queueCount) queued"
            : "Tasks"
        menu.addItem(actionItem(taskTitle, action: #selector(openTasks(_:))))
        menu.addItem(actionItem("Delivery", action: #selector(openDelivery(_:))))
        menu.addItem(actionItem("Projects", action: #selector(openProjects(_:))))
        let attentionCount = (snapshot.lastFailure == nil ? 0 : 1) + snapshot.failedDeliveries.count
        let attentionTitle = attentionCount > 0 ? "Attention · \(attentionCount)" : "Attention"
        menu.addItem(actionItem(attentionTitle, action: #selector(openAttention(_:))))
        menu.addItem(.separator())
        menu.addItem(actionItem("Settings…", action: #selector(openSettings(_:))))
        menu.addItem(usageMenuItem(snapshot: snapshot))
        menu.addItem(actionItem("Logs", action: #selector(openLogs(_:))))

        menu.addItem(.separator())
        menu.addItem(actionItem("Quit Codeshark", action: #selector(quitCodeshark)))
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
        if let bucket = snapshot.accountUsage?.buckets.first(where: { $0.limitID == "codex" }),
           let window = bucket.primary {
            addSecondary("Codex · \(window.usedPercent)% used · \(quotaWindowText(window))", to: usage)
        } else {
            addSecondary("Live Codex quota will appear after the next turn", to: usage)
        }
        let recentTokens = snapshot.modelUsage5h.reduce(0) { $0 + ($1.totalTokens ?? 0) }
        let weeklyTokens = snapshot.modelUsage7d.reduce(0) { $0 + ($1.totalTokens ?? 0) }
        addSecondary("Last 5 hours · \(tokenText(recentTokens))", to: usage)
        addSecondary("Last 7 days · \(tokenText(weeklyTokens))", to: usage)
        usage.addItem(.separator())
        usage.addItem(actionItem("Open Usage", action: #selector(openUsage(_:))))
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

    @objc private func openLocalConsole(_ sender: Any?) {
        showLocalConsole()
    }

    @objc private func openSettings(_ sender: Any?) {
        showSettings()
    }

    @objc private func openTasks(_ sender: Any?) {
        showTasks()
    }

    @objc private func openDelivery(_ sender: Any?) {
        showDelivery()
    }

    @objc private func openProjects(_ sender: Any?) {
        showProjects()
    }

    @objc private func openAttention(_ sender: Any?) {
        showAttention()
    }

    @objc private func openUsage(_ sender: Any?) {
        showUsage()
    }

    @objc private func openLogs(_ sender: Any?) {
        showLogs()
    }

    private func showSettings() {
        dashboard.refresh()
        if let panel = settingsPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 390),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Settings"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        let content = NSView(frame: panel.contentView?.bounds ?? .zero)
        let title = NSTextField(labelWithString: "Settings")
        title.font = .systemFont(ofSize: 17, weight: .semibold)
        title.frame = NSRect(x: 18, y: 350, width: 484, height: 23)
        content.addSubview(title)
        let detail = NSTextField(wrappingLabelWithString: "Configure where Codeshark works, how it routes work, and what it is allowed to do.")
        detail.font = .systemFont(ofSize: 12)
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 18, y: 320, width: 484, height: 22)
        content.addSubview(detail)

        func row(_ title: String, _ detail: String, _ action: Selector, y: CGFloat) {
            let button = NSButton(title: title, target: self, action: action)
            button.bezelStyle = .rounded
            button.frame = NSRect(x: 18, y: y + 7, width: 150, height: 28)
            content.addSubview(button)
            let label = NSTextField(wrappingLabelWithString: detail)
            label.font = .systemFont(ofSize: 11)
            label.textColor = .secondaryLabelColor
            label.frame = NSRect(x: 180, y: y, width: 322, height: 38)
            content.addSubview(label)
        }
        let workspace = dashboard.snapshot.workspacePath.isEmpty
            ? "Choose the working folder for new tasks."
            : workspaceDisplayPath(dashboard.snapshot.workspacePath)
        row("Workspace…", workspace, #selector(openSettingsWorkspace), y: 258)
        row("Model Routing…", "Assign models and reasoning effort to every orchestration role.", #selector(openSettingsModels), y: 204)
        row("Orchestration…", "Choose the supporting stages and feedback loops for each task tier.", #selector(openSettingsOrchestration), y: 150)
        row("Security…", "Set administrator, connector, network, and group-sandbox permissions.", #selector(openSettingsSecurity), y: 96)

        let separator = NSBox(frame: NSRect(x: 18, y: 44, width: 484, height: 1))
        separator.boxType = .separator
        content.addSubview(separator)
        let close = NSButton(title: "Close", target: self, action: #selector(closeSettings))
        close.bezelStyle = .rounded
        close.frame = NSRect(x: 418, y: 9, width: 84, height: 26)
        content.addSubview(close)
        panel.contentView = content
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        settingsPanel = panel
    }

    @objc private func closeSettings() {
        settingsPanel?.close()
    }

    @objc private func openSettingsWorkspace() {
        settingsPanel?.close()
        chooseWorkspace()
    }

    @objc private func openSettingsModels() {
        settingsPanel?.close()
        configureModels()
    }

    @objc private func openSettingsOrchestration() {
        settingsPanel?.close()
        configureOrchestration()
    }

    @objc private func openSettingsSecurity() {
        settingsPanel?.close()
        configureSecurity()
    }

    private func configureSecurity() {
        dashboard.refresh()
        if let panel = securityPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let security = dashboard.snapshot.security ?? DashboardSecurity(
            sandbox: "workspace-write",
            networkAccess: false,
            adminFullAccess: false,
            adminAutoApproveActions: false,
            adminMcpEnabled: true,
            adminDelegatedWriteAccess: true,
            groupNetworkAccess: true,
            groupWorkspaceWrite: true,
            telegram: "Keychain credential · one paired administrator",
            groups: []
        )
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 700, height: 600),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Security Settings"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self

        let content = NSView(frame: panel.contentView?.bounds ?? .zero)
        let title = NSTextField(labelWithString: "Security Settings")
        title.font = .systemFont(ofSize: 16, weight: .semibold)
        title.frame = NSRect(x: 20, y: 558, width: 660, height: 21)
        content.addSubview(title)
        let detail = NSTextField(wrappingLabelWithString: "Each switch has an independent effect. Changes save now and apply after active work finishes; the menu bar remains available.")
        detail.font = .systemFont(ofSize: 11)
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 20, y: 522, width: 660, height: 28)
        content.addSubview(detail)

        let execution = NSTextField(labelWithString: "ADMINISTRATOR EXECUTION")
        execution.font = .systemFont(ofSize: 10, weight: .semibold)
        execution.textColor = .secondaryLabelColor
        execution.frame = NSRect(x: 20, y: 492, width: 240, height: 14)
        content.addSubview(execution)
        let sandbox = NSTextField(labelWithString: "Default sandbox · \(security.sandbox)")
        sandbox.font = .systemFont(ofSize: 11)
        sandbox.textColor = .secondaryLabelColor
        sandbox.frame = NSRect(x: 420, y: 491, width: 260, height: 16)
        content.addSubview(sandbox)

        func toggle(_ title: String, checked: Bool, y: CGFloat) -> NSButton {
            let button = NSButton(checkboxWithTitle: title, target: nil, action: nil)
            button.state = checked ? .on : .off
            button.font = .systemFont(ofSize: 12)
            button.frame = NSRect(x: 20, y: y, width: 500, height: 20)
            content.addSubview(button)
            return button
        }
        let network = NSButton(checkboxWithTitle: "Allow network access", target: nil, action: nil)
        network.state = security.networkAccess ? .on : .off
        network.font = .systemFont(ofSize: 12)
        network.frame = NSRect(x: 20, y: 458, width: 500, height: 20)
        content.addSubview(network)
        let fullAccess = toggle("Allow administrator full filesystem access", checked: security.adminFullAccess, y: 430)
        let autoApprove = toggle("Automatically approve administrator actions", checked: security.adminAutoApproveActions, y: 402)
        let mcp = toggle("Enable configured MCP connectors", checked: security.adminMcpEnabled, y: 374)
        let delegatedWrite = toggle("Allow writes to configured delegated project roots", checked: security.adminDelegatedWriteAccess, y: 346)
        securityNetworkAccess = network
        securityAdminFullAccess = fullAccess
        securityAdminAutoApprove = autoApprove
        securityAdminMcp = mcp
        securityAdminDelegatedWrite = delegatedWrite

        let groups = NSTextField(labelWithString: "GROUP CHAT")
        groups.font = .systemFont(ofSize: 10, weight: .semibold)
        groups.textColor = .secondaryLabelColor
        groups.frame = NSRect(x: 20, y: 312, width: 180, height: 14)
        content.addSubview(groups)
        let groupNetwork = toggle("Allow non-admin group network research", checked: security.groupNetworkAccess, y: 278)
        let groupWrite = toggle("Allow non-admin group sandbox file writes", checked: security.groupWorkspaceWrite, y: 250)
        securityGroupNetwork = groupNetwork
        securityGroupWorkspaceWrite = groupWrite
        let enabledGroups = security.groups.isEmpty
            ? "No enabled groups."
            : security.groups.prefix(3).map { "\($0.title) (\($0.chatID))" }.joined(separator: " · ")
        let groupSummary = NSTextField(wrappingLabelWithString: "Enabled: \(enabledGroups)")
        groupSummary.font = .systemFont(ofSize: 11)
        groupSummary.textColor = .secondaryLabelColor
        groupSummary.frame = NSRect(x: 20, y: 211, width: 660, height: 28)
        content.addSubview(groupSummary)

        let fixed = NSTextField(labelWithString: "FIXED BOUNDARIES")
        fixed.font = .systemFont(ofSize: 10, weight: .semibold)
        fixed.textColor = .secondaryLabelColor
        fixed.frame = NSRect(x: 20, y: 178, width: 180, height: 14)
        content.addSubview(fixed)
        let groupPolicy = NSTextField(wrappingLabelWithString: "\(security.telegram). Group requests must mention or reply to Codeshark. Non-admin group work remains isolated from administrator memory, credentials, project roots, and MCP.")
        groupPolicy.font = .systemFont(ofSize: 11)
        groupPolicy.textColor = .secondaryLabelColor
        groupPolicy.frame = NSRect(x: 20, y: 130, width: 660, height: 42)
        content.addSubview(groupPolicy)

        let local = NSTextField(wrappingLabelWithString: "Local console: actions sent through Open Codeshark are direct owner requests on this Mac, with a separate session and the same configured sandbox.")
        local.font = .systemFont(ofSize: 11)
        local.textColor = .secondaryLabelColor
        local.frame = NSRect(x: 20, y: 78, width: 660, height: 32)
        content.addSubview(local)

        let separator = NSBox(frame: NSRect(x: 20, y: 43, width: 660, height: 1))
        separator.boxType = .separator
        content.addSubview(separator)
        let close = NSButton(title: "Close", target: self, action: #selector(closeSecurity))
        close.bezelStyle = .rounded
        close.frame = NSRect(x: 20, y: 9, width: 84, height: 26)
        content.addSubview(close)
        let apply = NSButton(title: "Apply", target: self, action: #selector(applySecurity))
        apply.bezelStyle = .rounded
        apply.keyEquivalent = "\r"
        apply.frame = NSRect(x: 596, y: 9, width: 84, height: 26)
        content.addSubview(apply)
        panel.contentView = content
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        securityPanel = panel
    }

    @objc private func closeSecurity() {
        securityPanel?.close()
    }

    @objc private func applySecurity() {
        guard let network = securityNetworkAccess,
              let fullAccess = securityAdminFullAccess,
              let autoApprove = securityAdminAutoApprove,
              let mcp = securityAdminMcp,
              let delegatedWrite = securityAdminDelegatedWrite,
              let groupNetwork = securityGroupNetwork,
              let groupWrite = securityGroupWorkspaceWrite
        else {
            showError("Could not read the security settings.")
            return
        }
        securityPanel?.close()
        runServiceCommand([
            "set-security",
            "--network", network.state == .on ? "true" : "false",
            "--admin-full-access", fullAccess.state == .on ? "true" : "false",
            "--admin-auto-approve-actions", autoApprove.state == .on ? "true" : "false",
            "--admin-mcp-enabled", mcp.state == .on ? "true" : "false",
            "--admin-delegated-write-access", delegatedWrite.state == .on ? "true" : "false",
            "--group-network-access", groupNetwork.state == .on ? "true" : "false",
            "--group-workspace-write", groupWrite.state == .on ? "true" : "false",
        ])
    }

    private func showLocalConsole() {
        if let panel = localConsolePanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let model = LocalConsoleModel { [weak self] arguments in
            self?.executeServiceCommand(arguments) ?? (status: 1, output: "Codeshark is unavailable.")
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 660, height: 650),
            styleMask: [.titled, .closable, .utilityWindow, .resizable],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark"
        panel.minSize = NSSize(width: 600, height: 560)
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: LocalConsoleView(
                model: model,
                dashboard: dashboard,
                chooseFiles: { [weak self] in self?.chooseLocalFiles() },
                revealArtifacts: { [weak self] paths in self?.revealArtifacts(paths) },
                revealWorkspace: { [weak self] in self?.revealWorkspace() },
                close: { [weak self] in self?.localConsolePanel?.close() }
            )
        )
        localConsoleModel = model
        localConsolePanel = panel
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func chooseLocalFiles() {
        let chooser = NSOpenPanel()
        chooser.canChooseFiles = true
        chooser.canChooseDirectories = false
        chooser.allowsMultipleSelection = true
        chooser.message = "Attach files to the local Codeshark task"
        guard chooser.runModal() == .OK else { return }
        localConsoleModel?.addAttachments(chooser.urls)
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
            + "\n\nThis changes Codeshark's working directory for new tasks. It saves now and restarts automatically after active work finishes."
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
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 520),
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
        title.font = .systemFont(ofSize: 16, weight: .semibold)
        title.frame = NSRect(x: 16, y: 484, width: 588, height: 20)
        content.addSubview(title)

        let detail = NSTextField(wrappingLabelWithString: "Settings save now; Codeshark restarts automatically after active work finishes.")
        detail.font = .systemFont(ofSize: 12)
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 16, y: 452, width: 588, height: 18)
        content.addSubview(detail)

        let modelHeader = NSTextField(labelWithString: "MODEL")
        modelHeader.font = .systemFont(ofSize: 10, weight: .semibold)
        modelHeader.textColor = .secondaryLabelColor
        modelHeader.frame = NSRect(x: 170, y: 426, width: 245, height: 14)
        content.addSubview(modelHeader)
        let effortHeader = NSTextField(labelWithString: "REASONING")
        effortHeader.font = .systemFont(ofSize: 10, weight: .semibold)
        effortHeader.textColor = .secondaryLabelColor
        effortHeader.frame = NSRect(x: 425, y: 426, width: 179, height: 14)
        content.addSubview(effortHeader)

        let roles = [
            ("Quick / Routine", "Routine", "gpt-5.6-luna", "medium"),
            ("Planner / Triage", "Preflight", "gpt-5.6-luna", "low"),
            ("Research", "Research", "gpt-5.6-luna", "medium"),
            ("Primary", "Primary", "gpt-5.6-sol", "high"),
            ("Rework", "Rework", "gpt-5.6-sol", "high"),
            ("Independent Review", "Validation", "gpt-5.6-terra", "high"),
            ("Adversarial Review", "Feedback", "gpt-5.6-terra", "high"),
            ("Finalization", "Finalization", "gpt-5.6-sol", "medium"),
        ]
        modelOptions = availableModelOptions()
        modelPickers = [:]
        reasoningPickers = [:]
        for (index, role) in roles.enumerated() {
            let y = 370 - (index * 39)
            let label = NSTextField(labelWithString: role.0)
            label.font = .systemFont(ofSize: 12, weight: .medium)
            label.frame = NSRect(x: 16, y: y + 18, width: 145, height: 16)
            content.addSubview(label)

            let assignment = dashboard.snapshot.modelAssignments.first(where: { $0.role == role.1 })
            let current = assignment?.model ?? role.2
            let currentEffort = assignment?.reasoningEffort ?? role.3
            let recentUsage = NSTextField(
                labelWithString: "7d · \(tokenText(assignment?.recentTotalTokens ?? 0)) · \(assignment?.recentMeasuredTurns ?? 0)/\(assignment?.recentRuns ?? 0) turns"
            )
            recentUsage.font = .systemFont(ofSize: 9)
            recentUsage.textColor = .secondaryLabelColor
            recentUsage.frame = NSRect(x: 16, y: y + 3, width: 145, height: 12)
            content.addSubview(recentUsage)
            let modelPicker = modelPicker(
                current,
                role: role.1,
                frame: NSRect(x: 170, y: y + 7, width: 245, height: 26)
            )
            let effortPicker = reasoningPicker(
                model: current,
                current: currentEffort,
                frame: NSRect(x: 425, y: y + 7, width: 179, height: 26)
            )
            modelPicker.font = .systemFont(ofSize: 12)
            effortPicker.font = .systemFont(ofSize: 12)
            content.addSubview(modelPicker)
            content.addSubview(effortPicker)
            modelPickers[role.1] = modelPicker
            reasoningPickers[role.1] = effortPicker
        }

        let separator = NSBox(frame: NSRect(x: 16, y: 44, width: 588, height: 1))
        separator.boxType = .separator
        content.addSubview(separator)

        let close = NSButton(title: "Close", target: self, action: #selector(closeModelRouting))
        close.bezelStyle = .rounded
        close.frame = NSRect(x: 16, y: 10, width: 84, height: 26)
        content.addSubview(close)

        let apply = NSButton(title: "Apply", target: self, action: #selector(applyModelRouting))
        apply.bezelStyle = .rounded
        apply.keyEquivalent = "\r"
        apply.frame = NSRect(x: 520, y: 10, width: 84, height: 26)
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
              let researchPicker = modelPickers["Research"],
              let research = selectedModel(researchPicker),
              let researchEffort = reasoningPickers["Research"]?.titleOfSelectedItem,
              let primaryPicker = modelPickers["Primary"],
              let primary = selectedModel(primaryPicker),
              let primaryEffort = reasoningPickers["Primary"]?.titleOfSelectedItem,
              let reworkPicker = modelPickers["Rework"],
              let rework = selectedModel(reworkPicker),
              let reworkEffort = reasoningPickers["Rework"]?.titleOfSelectedItem,
              let validatorPicker = modelPickers["Validation"],
              let validator = selectedModel(validatorPicker),
              let validatorEffort = reasoningPickers["Validation"]?.titleOfSelectedItem,
              let feedbackPicker = modelPickers["Feedback"],
              let feedback = selectedModel(feedbackPicker),
              let feedbackEffort = reasoningPickers["Feedback"]?.titleOfSelectedItem,
              let finalizerPicker = modelPickers["Finalization"],
              let finalizer = selectedModel(finalizerPicker),
              let finalizerEffort = reasoningPickers["Finalization"]?.titleOfSelectedItem
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
            "--research", research,
            "--research-effort", researchEffort,
            "--primary", primary,
            "--primary-effort", primaryEffort,
            "--rework", rework,
            "--rework-effort", reworkEffort,
            "--validator", validator,
            "--validator-effort", validatorEffort,
            "--feedback", feedback,
            "--feedback-effort", feedbackEffort,
            "--finalizer", finalizer,
            "--finalizer-effort", finalizerEffort,
        ])
    }

    private func configureOrchestration() {
        dashboard.refresh()
        if let panel = orchestrationPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 330),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Orchestration"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self

        let content = NSView(frame: panel.contentView?.bounds ?? .zero)
        let title = NSTextField(labelWithString: "Orchestration")
        title.font = .systemFont(ofSize: 16, weight: .semibold)
        title.frame = NSRect(x: 16, y: 294, width: 728, height: 20)
        content.addSubview(title)
        let detail = NSTextField(
            wrappingLabelWithString: "Quick: one pass. Routine: scoped checks. Review begins at Standard. Settings restart after active work finishes."
        )
        detail.font = .systemFont(ofSize: 11)
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 16, y: 263, width: 728, height: 16)
        content.addSubview(detail)

        for (title, x, width) in [
            ("PLANNER", 170, 90),
            ("RESEARCH", 285, 90),
            ("INDEPENDENT REVIEW", 375, 160),
            ("REWORK LOOPS", 545, 110),
            ("FINALIZER", 675, 90),
        ] {
            let header = NSTextField(labelWithString: title)
            header.font = .systemFont(ofSize: 10, weight: .semibold)
            header.textColor = .secondaryLabelColor
            header.frame = NSRect(x: CGFloat(x), y: 235, width: CGFloat(width), height: 14)
            content.addSubview(header)
        }

        let tiers = [
            ("quick", "Quick"),
            ("routine", "Routine"),
            ("standard", "Standard"),
            ("deep", "Deep"),
            ("high_assurance", "High assurance"),
        ]
        orchestrationPreflight = [:]
        orchestrationResearch = [:]
        orchestrationValidation = [:]
        orchestrationFeedback = [:]
        orchestrationFinalization = [:]
        for (index, tier) in tiers.enumerated() {
            let y = 195 - (index * 30)
            let values = orchestrationValues(for: tier.0)
            let label = NSTextField(labelWithString: tier.1)
            label.font = .systemFont(ofSize: 12, weight: .medium)
            label.frame = NSRect(x: 16, y: y + 4, width: 135, height: 18)
            content.addSubview(label)
            let preflight = checkbox(checked: values.usesPreflight, frame: NSRect(x: 200, y: y + 2, width: 20, height: 20))
            let research = checkbox(checked: values.usesResearch, frame: NSRect(x: 315, y: y + 2, width: 20, height: 20))
            let validation = checkbox(checked: values.usesValidator, frame: NSRect(x: 445, y: y + 2, width: 20, height: 20))
            let feedback = NSPopUpButton(frame: NSRect(x: 560, y: y, width: 70, height: 25), pullsDown: false)
            feedback.font = .systemFont(ofSize: 12)
            feedback.addItems(withTitles: ["0", "1", "2", "3", "4", "5"])
            feedback.selectItem(withTitle: String(values.feedbackIterations))
            let finalization = checkbox(checked: values.usesFinalizer, frame: NSRect(x: 705, y: y + 2, width: 20, height: 20))
            content.addSubview(preflight)
            content.addSubview(research)
            content.addSubview(validation)
            content.addSubview(feedback)
            content.addSubview(finalization)
            orchestrationPreflight[tier.0] = preflight
            orchestrationResearch[tier.0] = research
            orchestrationValidation[tier.0] = validation
            orchestrationFeedback[tier.0] = feedback
            orchestrationFinalization[tier.0] = finalization
        }

        let separator = NSBox(frame: NSRect(x: 16, y: 42, width: 728, height: 1))
        separator.boxType = .separator
        content.addSubview(separator)
        let close = NSButton(title: "Close", target: self, action: #selector(closeOrchestration))
        close.bezelStyle = .rounded
        close.frame = NSRect(x: 16, y: 9, width: 84, height: 26)
        content.addSubview(close)
        let apply = NSButton(title: "Apply", target: self, action: #selector(applyOrchestration))
        apply.bezelStyle = .rounded
        apply.keyEquivalent = "\r"
        apply.frame = NSRect(x: 660, y: 9, width: 84, height: 26)
        content.addSubview(apply)
        panel.contentView = content
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        orchestrationPanel = panel
    }

    private func orchestrationValues(for tier: String) -> DashboardOrchestrationTier {
        let configured = dashboard.snapshot.orchestration
        switch tier {
        case "quick":
            return configured?.quick ?? DashboardOrchestrationTier()
        case "routine":
            return configured?.routine ?? DashboardOrchestrationTier()
        case "standard":
            return configured?.standard ?? DashboardOrchestrationTier(usesValidator: true, usesFinalizer: true)
        case "deep":
            return configured?.deep ?? DashboardOrchestrationTier(
                usesPreflight: true,
                usesValidator: true,
                feedbackIterations: 1,
                usesFinalizer: true
            )
        default:
            return configured?.highAssurance ?? DashboardOrchestrationTier(
                usesPreflight: true,
                usesResearch: true,
                usesValidator: true,
                feedbackIterations: 2,
                usesFinalizer: true
            )
        }
    }

    private func checkbox(checked: Bool, frame: NSRect) -> NSButton {
        let button = NSButton(checkboxWithTitle: "", target: nil, action: nil)
        button.state = checked ? .on : .off
        button.frame = frame
        return button
    }

    @objc private func closeOrchestration() {
        orchestrationPanel?.orderOut(nil)
    }

    @objc private func applyOrchestration() {
        let tiers = ["quick", "routine", "standard", "deep", "high_assurance"]
        var arguments = ["set-orchestration"]
        for tier in tiers {
            guard let preflight = orchestrationPreflight[tier],
                  let research = orchestrationResearch[tier],
                  let validation = orchestrationValidation[tier],
                  let feedback = orchestrationFeedback[tier]?.titleOfSelectedItem,
                  let loops = Int(feedback),
                  let finalization = orchestrationFinalization[tier]
            else {
                showError("Could not read the orchestration settings.")
                return
            }
            if loops > 0 && validation.state != .on {
                showError("\(tier.capitalized) feedback loops require validation.")
                return
            }
            if (preflight.state == .on || research.state == .on) && validation.state != .on {
                showError("\(tier.capitalized) planning and research require validation.")
                return
            }
            if finalization.state == .on && validation.state != .on {
                showError("\(tier.capitalized) finalization requires validation.")
                return
            }
            let option = tier.replacingOccurrences(of: "_", with: "-")
            arguments += [
                "--\(option)-planning", preflight.state == .on ? "true" : "false",
                "--\(option)-research", research.state == .on ? "true" : "false",
                "--\(option)-validation", validation.state == .on ? "true" : "false",
                "--\(option)-feedback-loops", String(loops),
                "--\(option)-finalization", finalization.state == .on ? "true" : "false",
            ]
        }
        orchestrationPanel?.orderOut(nil)
        runServiceCommand(arguments)
    }

    private func showUsage() {
        dashboard.refresh()
        if let panel = usagePanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 580, height: 732),
            styleMask: [.titled, .closable, .utilityWindow, .resizable],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Model Usage"
        panel.minSize = NSSize(width: 560, height: 712)
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

    private func showTasks() {
        dashboard.refresh()
        if let panel = taskPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 430),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Tasks"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: TaskQueueView(
                model: dashboard,
                showLogs: { [weak self] in self?.showLogs() },
                close: { [weak self] in self?.taskPanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        taskPanel = panel
    }

    private func showDelivery() {
        dashboard.refresh()
        if let panel = deliveryPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 500, height: 470),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Delivery"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: DeliveryCenterView(
                model: dashboard,
                showLogs: { [weak self] in self?.showLogs() },
                revealArtifacts: { [weak self] paths in self?.revealArtifacts(paths) },
                close: { [weak self] in self?.deliveryPanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        deliveryPanel = panel
    }

    private func showProjects() {
        dashboard.refresh()
        if let panel = projectsPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 500, height: 420),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Projects"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: ProjectOverviewView(
                model: dashboard,
                revealWorkspace: { [weak self] in self?.revealWorkspace() },
                close: { [weak self] in self?.projectsPanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        projectsPanel = panel
    }

    private func showAttention() {
        dashboard.refresh()
        if let panel = attentionPanel {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 360),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )
        panel.title = "Codeshark Attention"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentViewController = NSHostingController(
            rootView: AttentionView(
                model: dashboard,
                showLogs: { [weak self] in self?.showLogs() },
                close: { [weak self] in self?.attentionPanel?.close() }
            )
        )
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        attentionPanel = panel
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
        } else if window == settingsPanel {
            settingsPanel = nil
        } else if window == orchestrationPanel {
            orchestrationPanel = nil
            orchestrationPreflight = [:]
            orchestrationResearch = [:]
            orchestrationValidation = [:]
            orchestrationFeedback = [:]
            orchestrationFinalization = [:]
        } else if window == securityPanel {
            securityPanel = nil
            securityNetworkAccess = nil
            securityAdminFullAccess = nil
            securityAdminAutoApprove = nil
            securityAdminMcp = nil
            securityAdminDelegatedWrite = nil
            securityGroupNetwork = nil
            securityGroupWorkspaceWrite = nil
        } else if window == localConsolePanel {
            localConsolePanel = nil
            localConsoleModel = nil
        } else if window == usagePanel {
            usagePanel = nil
        } else if window == taskPanel {
            taskPanel = nil
        } else if window == deliveryPanel {
            deliveryPanel = nil
        } else if window == projectsPanel {
            projectsPanel = nil
        } else if window == attentionPanel {
            attentionPanel = nil
        } else if window == logPanel {
            logPanel = nil
        }
    }

    private func revealLogFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: projectRoot).appendingPathComponent("runtime"))
    }

    private func revealWorkspace() {
        dashboard.refresh()
        let path = dashboard.snapshot.workspacePath
        guard !path.isEmpty else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    private func revealArtifacts(_ paths: [String]) {
        let files = paths.compactMap { path -> URL? in
            let url = URL(fileURLWithPath: path)
            guard (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
                return nil
            }
            return url
        }
        guard !files.isEmpty else {
            showError("The delivered file is no longer available locally.")
            return
        }
        NSWorkspace.shared.activateFileViewerSelecting(files)
    }

    private func executeServiceCommand(_ arguments: [String]) -> (status: Int32, output: String) {
        guard let python = servicePython() else {
            return (status: 1, output: "Could not find the Codeshark service Python runtime.")
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
            return (status: 1, output: "Could not run Codeshark: \(error.localizedDescription)")
        }
        let detail = String(
            data: output.fileHandleForReading.readDataToEndOfFile(),
            encoding: .utf8
        ) ?? ""
        return (status: command.terminationStatus, output: detail)
    }

    private func runServiceCommand(_ arguments: [String]) {
        let result = executeServiceCommand(arguments)
        if result.status != 0 {
            showError(result.output.isEmpty ? "Could not apply the setting." : result.output)
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
