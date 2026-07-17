# Security Policy

Codex-codeshark connects Telegram input to a local agent runtime. Security reports are taken seriously, especially when they involve authentication bypass, secret exposure, workspace escape, approval bypass, unsafe migration archives, or unintended external side effects.

## Supported versions

| Version | Supported |
|---|---|
| Latest commit on `main` | Yes |
| Older commits or forks | No |

Until the first stable release, security fixes are made on `main` only.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting or a private security advisory for this repository. Include:

- The affected commit or version
- Preconditions and configuration
- Reproduction steps or a minimal proof of concept
- Expected and actual behavior
- Potential impact
- Any suggested mitigation

Do not include real Telegram tokens, Codex credentials, personal data, or unrelated secrets. Replace them with clearly marked test values.

## Security boundaries

The intended boundaries are:

- One explicitly paired Telegram administrator in a private chat
- With the default `admin_full_access = false`, unapproved administrator tasks are forced into a read-only Codex sandbox with network, MCP, apps, browser/computer control, and additional writable roots disabled
- With the default configuration, state-changing administrator requests wait for explicit approval before receiving the configured `workspace-write`, network, MCP, and `delegated_roots` capabilities
- Optional `admin_full_access = true` for the paired administrator only: private tasks use Codex `danger-full-access`, including plugin installation, live network access, and configured MCP servers without a task-level approval pause
- Optional administrator-configured read-only roots and writable delegated project roots for trusted private-chat work
- Group access denied by default and enabled only by the paired administrator
- Group members limited to explicit bot mentions in an enabled group, with no attachments or control commands
- Group continuity scoped to each `(group, requester)`, bounded to six exchanges with 30-day expiry, excluded from administrator learning and migration exports
- A separate ephemeral group Codex runtime outside the repository, using a least-privilege filesystem permission profile that can read only its empty workspace and minimal runtime files
- Group network, web search, apps, browser/computer control, MCP, memories, multi-agent execution, and write access disabled
- A mandatory MCP server inventory and per-tool allowlist
- Explicit approval for requests classified as destructive or externally mutating
- Bot tokens stored in macOS Keychain and a strict Codex child-environment allowlist
- Outbound Codex network access disabled by default and explicitly configured per child
- Size-limited Telegram attachments stored only in the server-controlled workspace
- A versioned owner-only LaunchAgent source snapshot outside delegated project roots, with owner-only runtime storage and atomic private-file replacement

The administrator-side risk classifier and model instructions are defense-in-depth controls. `admin_full_access = true` intentionally removes the private-chat sandbox and approval boundary; use it only for a single trusted paired administrator. Guest isolation additionally relies on Codex permission profiles and therefore requires Codex CLI 0.138.0 or newer; startup rejects older versions.

The Codex child receives only basic process, locale, temporary-directory, certificate, and Codex-home variables. Parent API keys, Telegram credentials, cloud credentials, and SSH-agent sockets are not forwarded. Credential-bearing MCP tools remain a separate trust boundary and should stay disabled unless required.

Group tasks use an isolated Codex home containing only a symlink to the existing Codex authentication file plus Codex-generated caches. The filesystem profile prevents model-generated commands from reading that home. Ephemeral task databases, logs, shell snapshots, and other non-cache state are removed after each group request. The gateway separately stores bounded requester-scoped exchanges for continuity; disabling a group deletes them. Enabled group IDs, participant context, and group request records are deliberately excluded from migration exports.

Private administrator tasks may trigger model-initiated automatic learning. The model is instructed to learn only durable, high-value patterns and to exclude secrets, credentials, speculation, and unnecessary sensitive data. The gateway automatically applies a candidate only when its content exactly matches non-secret evidence in the current authenticated administrator request. Ungrounded, inferred, or session-summary candidates remain pending for explicit review. Automatic learning is never sourced from group or scheduled tasks. Administrators can audit events with `/learning` and inspect, approve, reject, or delete learned data with `/approve`, `/reject`, `/memories`, `/skills`, `/forget`, and `/forget_skill`.

When upgrading to a provenance-aware release, previously auto-applied private-task candidates linked to a task but without a recorded approval basis are quarantined back to pending review and their matching injected memory or skill is removed. This one-time migration intentionally favors safety over retaining unverified model output.
