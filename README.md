<div align="center">
  <img src="assets/codeshark-mascot.png" alt="Codex-codeshark mascot" width="320">
  <h1>Codex-codeshark</h1>
  <p><strong>A private, always-on Telegram control plane for your local OpenAI Codex CLI.</strong></p>
  <p>
    <a href="https://github.com/Younghegalian/codeshark/actions/workflows/tests.yml"><img src="https://github.com/Younghegalian/codeshark/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
    <a href="https://www.apple.com/macos/"><img src="https://img.shields.io/badge/platform-macOS-000000?logo=apple&amp;logoColor=white" alt="macOS"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="MIT License"></a>
    <a href="pyproject.toml"><img src="https://img.shields.io/badge/runtime_dependencies-0-2ea44f" alt="Zero runtime dependencies"></a>
  </p>
  <p>
    <a href="#quick-start">Quick start</a> ·
    <a href="#what-it-does">Features</a> ·
    <a href="#security-defaults">Security</a> ·
    <a href="#telegram-command-reference">Commands</a> ·
    <a href="#upgrading">Upgrading</a>
  </p>
</div>

Codex-codeshark connects one authenticated administrator chat to a sandboxed Codex session on your Mac. It keeps work queued across restarts, runs scheduled checks, proposes durable memories and reusable skills, and can answer natural-language mentions in administrator-enabled Telegram groups.

It uses your existing Codex login. The project does not require a separate model API key, does not copy ChatGPT credentials into the repository, and stores the Telegram bot token in macOS Keychain.

> [!IMPORTANT]
> Codex-codeshark is intentionally a **single-administrator, Telegram-only, macOS gateway**. Group members are unprivileged guests, not additional administrators. It is not a hosted bot service or a multi-agent framework.

## Why Codex-codeshark?

Open-ended agent frameworks are powerful, but a personal coding gateway benefits from a smaller and more inspectable security boundary. Codex-codeshark focuses on one channel, one administrator, explicit guest-group access, and one local Codex runtime.

| Principle | What it means here |
|---|---|
| Local first | Codex runs on your Mac; writes stay inside a server-controlled workspace. |
| One administrator | Exactly one paired Telegram user ID receives sessions, memory, tools, and control commands. |
| Bounded guests | Only explicit `@bot` mentions in enabled groups enter a separate ephemeral and filesystem-isolated runtime. |
| Approval gated | Learning and risky external actions wait for explicit approval. |
| Durable, not unbounded | Queues, sessions, memories, skills, feedback, and failed deliveries have retention limits. |
| Fail closed | Unlisted MCP servers or tools prevent startup instead of silently becoming available. |
| Portable personal data | Memories, skills, feedback, and schedules can move without exporting secrets. |

## What it does

- **Persistent conversation** — continues one Codex thread across Telegram messages and process restarts.
- **Administrator-enabled groups** — answers `@bot natural-language request` without sharing administrator sessions, memory, custom skills, projects, attachments, network, MCP, or write access.
- **Delegated project development** — lets the administrator inspect and modify server-configured project roots while keeping destructive and external actions behind approval.
- **Durable task queue** — stores queued work in SQLite and executes exactly one task at a time.
- **Scheduled work** — supports one-time reminders, heartbeat intervals, and five-field cron expressions.
- **Ephemeral automation** — scheduled jobs use `codex exec --ephemeral` and do not create conversation history.
- **Approval-gated learning** — lets Codex propose long-term memories and reusable skills without silently applying them.
- **Relevant skill loading** — injects at most three approved skills selected for the current request.
- **Searchable recall** — searches approved memories and skills with source IDs and task provenance.
- **Feedback-aware learning** — tracks usage and ratings, ranks equally relevant skills, and surfaces memories that need review.
- **Bounded sessions** — summarizes durable context for review, deletes the full session, and starts fresh at the configured turn limit.
- **Risk approval** — holds destructive or external-state requests until `/approve` is received.
- **MCP policy** — disables every server and tool that is not explicitly allowed for this gateway.
- **Quiet task delivery** — sends no queue/start chatter; Telegram receives only approval prompts, errors, and final results.
- **Reliable replies** — handles Telegram rate limits and keeps a bounded failed-delivery queue for explicit retry.
- **Safe attachments** — downloads Telegram photos and documents into a private, gitignored `workspace/inbox/` directory.
- **First-class service CLI** — installs, starts, stops, restarts, inspects, and safely reads the macOS service.
- **Portable migration** — exports personal data in a versioned, checksummed archive without tokens or local configuration.
- **Automated releases** — validates versions and signed tags, runs tests, builds packages, and publishes GitHub releases.
- **Zero runtime dependencies** — uses only the Python standard library at runtime.

## Quick start

### Requirements

- macOS
- Python 3.11 or newer
- [Codex desktop](https://openai.com/codex/) installed at `/Applications/Codex.app` with Codex CLI 0.138.0 or newer
- An active Codex login
- A Telegram bot token created with [BotFather](https://t.me/BotFather)

### 1. Clone

```bash
git clone https://github.com/Younghegalian/codeshark.git Codex-codeshark
cd Codex-codeshark
```

Codex-codeshark is currently installed from source; it is not published to PyPI. Packaged
GitHub release artifacts use `~/.codex-codeshark/` for private configuration and runtime data
unless `CODEX_CODESHARK_HOME` is set.

### 2. Set up and pair Telegram

```bash
PYTHONPATH=src python3 -m codex_codeshark setup
```

The setup flow:

1. Verifies the existing Codex login.
2. Accepts the BotFather token through hidden input.
3. Stores the token in macOS Keychain.
4. Displays a one-time pairing command such as `/pair A1B2C3D4`.
5. Accepts that command from one Telegram private chat within three minutes.
6. Creates the local configuration, administrator profile, and isolated group runtime.
7. Registers separate English command menus for private and group chats.

Paste only the BotFather token at the hidden prompt. Do not paste the BotFather message or a shell command.

### 3. Diagnose the installation

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

A healthy installation reports `PASS` for:

- Local configuration
- Telegram token in Keychain
- Telegram API access
- Codex login
- Codex CLI permission-profile support
- Administrator Codex profile
- Isolated group runtime
- Effective Codex model
- MCP allowlist consistency

### 4. Run it

Foreground mode is useful for the first test:

```bash
PYTHONPATH=src python3 -m codex_codeshark run
```

Send `/status` to the bot, then stop the foreground process with `Ctrl+C`.

For an always-on gateway, install and start the macOS LaunchAgent:

```bash
PYTHONPATH=src python3 -m codex_codeshark start
```

Manage and inspect it with the same CLI:

```bash
PYTHONPATH=src python3 -m codex_codeshark service-status
PYTHONPATH=src python3 -m codex_codeshark logs --lines 100
PYTHONPATH=src python3 -m codex_codeshark restart
PYTHONPATH=src python3 -m codex_codeshark stop
```

The compatibility scripts remain available for direct install and removal:

```bash
python3 scripts/install_launch_agent.py
python3 scripts/uninstall_launch_agent.py
```

### Optional: enable one Telegram group

For natural-language mentions, use BotFather's `/setprivacy` command to **disable Privacy Mode** for this bot. Telegram's [privacy-enabled bot rules](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get) do not deliver ordinary mention messages; the gateway still discards every group message that does not explicitly contain the bot username. Then add the bot to a group and send:

```text
/enable_group@YourBotUsername
@YourBotUsername Explain what a Python context manager does
```

Only the paired administrator can enable or disable a group. Group members use a normal message containing `@YourBotUsername`; unmentioned messages are ignored after receipt. Disable access in the group with `/disable_group@YourBotUsername`, or from the administrator's private chat with `/disable_group CHAT_ID`. `/groups` lists the current allowlist.

Disabling Privacy Mode means Telegram delivers group messages to the bot process. Codex-codeshark does not queue, store, or answer unmentioned messages. If you prefer Telegram not to deliver them at all, keep Privacy Mode enabled and group mention mode will not work.

## Security defaults

Codex-codeshark connects an agent runtime to a real messaging surface. Treat every inbound message as untrusted until the pairing and policy checks have accepted it.

- Exactly one Telegram user ID is the administrator.
- Groups are denied by default and can be enabled only by that paired administrator.
- Enabled groups accept only text that explicitly mentions the bot; unmentioned text, attachments, and control commands from guests are ignored.
- The BotFather token is stored in macOS Keychain, not in project files.
- The Codex child process receives a strict environment allowlist; Telegram, OpenAI API,
  cloud, GitHub, and SSH-agent credentials from the parent are not forwarded.
- Telegram cannot choose the workspace path or pass arbitrary Codex CLI flags.
- Administrator tasks run with `sandbox_mode = "workspace-write"`, server-controlled `delegated_roots`, and `approval_policy = "never"`.
- Guest requests use a separate Codex home, an empty workspace outside the repository, an ephemeral session, and a least-privilege [Codex permission profile](https://learn.chatgpt.com/docs/permissions) that grants read access only to that empty workspace and minimal runtime files.
- Guest web search, network, apps, browser/computer control, MCP servers, memories, multi-agent execution, and image generation are disabled. The isolated Codex state is cleaned after each request.
- Codex network access is disabled by default and explicitly set on every child process.
- Attachment paths are generated by the gateway, size-limited, privately stored, and confined to `workspace/inbox/`.
- Only one Codex task runs at a time, with cancellation and a configurable timeout.
- Requests classified as destructive or externally mutating wait for explicit approval.
- Interrupted approved tasks require approval again after restart.
- Every configured MCP server must be represented in the gateway policy.
- Servers without an explicit tool allowlist are disabled.

The administrator-side text classifier and injected execution policy are defense-in-depth controls. Group filesystem and network restrictions are enforced separately by the Codex permission profile. Keep credential-bearing MCP tools disabled unless required, do not enable unknown groups, and do not expose this bot as a public service. Enable `codex_network_access` only when an administrator task genuinely needs outbound access.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and the supported-version policy.

## How it works

```text
Administrator private chat                 Enabled Telegram group
        |                                           |
        v                                           v
Paired user ID + risk approval gate         Group allowlist + explicit @mention
        |                                           |
        v                                           v
Session + memory + approved skills          Ephemeral, isolated Codex home
        |                                           |
        v                                           v
workspace + delegated project writes       Empty read-only workspace; no tools/network
        |                                           |
        +----------------> final replies <----------+
```

Telegram is the authenticated transport and control plane. Codex performs reasoning and tool execution. Administrator writes are confined to `workspace/` plus `delegated_roots`; `read_only_roots` remains available for inspection-only locations. Group members never enter that runtime.

## Telegram command reference

### Sessions and tasks

| Command | Purpose |
|---|---|
| Plain text | Queue a task in the current interactive Codex session; only the final result is sent. |
| Photo or document | Save the attachment under `workspace/inbox/` and queue the caption as its task. |
| `/status` | Show active work, queue depth, session capacity, and stored item counts. |
| `/tasks` | List recent persistent task records. |
| `/cancel` | Cancel the active Codex process or the oldest queued task. |
| `/new` | Permanently delete the current Codex session and start fresh. |

### Group access

| Command | Who can use it | Purpose |
|---|---|---|
| `/enable_group` | Paired administrator, in the group | Allow that group to send restricted mention requests. |
| `/disable_group` | Paired administrator, in the group | Revoke access immediately. |
| `/group_status` | Paired administrator, in the group | Show whether that group is enabled. |
| `@BotUsername REQUEST` | Any member of an enabled group | Run one isolated, read-only, ephemeral natural-language request. |
| `/groups` | Paired administrator, private chat | List enabled group IDs and titles. |
| `/disable_group CHAT_ID` | Paired administrator, private chat | Revoke one group without entering it. |

### Memory, skills, and feedback

| Command | Purpose |
|---|---|
| `/remember TEXT` | Store an explicitly approved long-term memory. |
| `/memories` | List approved long-term memories. |
| `/forget ID` | Delete a long-term memory. |
| `/recall QUERY` | Search approved memories and skills with provenance and quality counters. |
| `/review_memories` | List never-used, stale, or negatively rated memories for review. |
| `/learn memory TEXT` | Create a memory proposal. |
| `/learn skill NAME \| PROCEDURE` | Create a reusable skill proposal. |
| `/learning` | List pending learning proposals. |
| `/approve ID` | Approve a learning proposal, risky task, or risky scheduled job. |
| `/reject ID` | Reject a pending proposal, task, or job. |
| `/skills` | List approved local skills. |
| `/forget_skill ID` | Delete an approved skill. |
| `/good [NOTE]` | Positively rate the last successful task. |
| `/bad [REASON]` | Negatively rate the last successful task. |

### Delivery recovery

| Command | Purpose |
|---|---|
| `/deliveries` | List final replies that Telegram did not accept or whose delivery was ambiguous. |
| `/retry_delivery ID` | Explicitly retry one failed reply and purge its stored text after success. |

### Automation and policy

| Command | Purpose |
|---|---|
| `/remind MINUTES REQUEST` | Run a request once after a delay. |
| `/heartbeat MINUTES REQUEST` | Run a periodic check. |
| `/cron EXPRESSION \| REQUEST` | Run a request on a local-time five-field cron schedule. |
| `/jobs` | List scheduled jobs. |
| `/pause ID` | Pause a scheduled job. |
| `/resume_job ID` | Resume a paused scheduled job. |
| `/delete_job ID` | Delete a scheduled job. |
| `/mcp` | Show the effective MCP server and tool policy. |
| `/help` | Show the command summary. |

## Approval-gated learning

Codex may append a hidden structured proposal when a successful task reveals a durable preference, fact, or reusable procedure. The gateway removes that block from the Telegram response and stages it for review.

```text
Task succeeds
    -> Codex proposes memory or skill
    -> gateway stores proposal as pending
    -> /approve applies it
       or /reject discards it
```

Nothing is learned silently:

1. Codex or the user proposes a memory or skill.
2. The proposal appears under `/learning`.
3. The user applies it with `/approve ID` or discards it with `/reject ID`.

Approved memories become durable context. Approved skills are selected by keyword relevance and loaded only when needed. Usage and `/good` or `/bad` feedback break ties between equally relevant skills. Approving a skill with an existing name replaces its procedure instead of creating an unbounded set of copies.

## Sessions and scheduled work

Interactive Telegram requests continue the current persisted Codex session. The session ID and turn count are stored in `runtime/state.json`.

When `max_session_turns` is reached, Codex creates a durable-summary proposal. The gateway deletes the old Codex session only after the proposal is staged successfully. If summarization or deletion fails, the existing session is kept.

Scheduled jobs are always ephemeral. They do not create or continue Codex sessions. A recurring job cannot enqueue another run while its previous run is active, preventing an unbounded backlog.

## Configuration and MCP policy

`setup` creates a gitignored `config.local.toml` containing installation-specific values:

- The paired Telegram user ID
- The fixed workspace path
- The Codex binary and profile
- Polling, timeout, queue, session, and memory limits
- The attachment size limit and explicit Codex network policy
- Server-controlled read-only and delegated writable project roots
- The MCP server inventory and per-server tool allowlist

It does not contain the BotFather token or conversation transcripts. It is still private because it includes a Telegram user ID and local filesystem paths.

See [config.example.toml](config.example.toml) for the complete schema.

For example, this lets the private administrator work across local projects as a delegated development agent:

```toml
delegated_roots = ["/Users/yourname/workspace"]
```

The active model is inherited from the normal Codex configuration and profile. `/status` and `doctor` report the effective model; the isolated group runtime is pinned to the same model without loading the administrator's configuration, memories, or project instructions.

### MCP policy example

```toml
[mcp_policy]
known_servers = ["github", "docs"]

[mcp_policy.allowed_tools]
docs = ["search", "fetch"]
# github is known but disabled for this gateway
```

At setup time, MCP server names found in the global Codex configuration and the `codex-codeshark` profile are copied into `known_servers`. No MCP tools are enabled automatically. Startup fails closed when the live MCP inventory and local policy do not match.

## Data retention

Codex-codeshark stores enough state to resume useful work without building an unbounded duplicate transcript archive.

| Store | Retention policy |
|---|---|
| `runtime/state.json` | Current session ID, turn count, and Telegram update offset only. |
| Interactive Codex session | Deleted and rotated at `max_session_turns` after staging a summary proposal. |
| Scheduled Codex runs | Ephemeral; no Codex session is stored. |
| Group Codex runs | Ephemeral; isolated runtime databases and shell snapshots are removed after each request. |
| Enabled group allowlist | Stored locally in SQLite; maximum 20 groups; excluded from personal-data migration. |
| Task records in `runtime/agent.db` | Raw prompts are cleared on terminal status; 200 terminal records are retained. |
| Learning proposals | Up to 100 pending proposals and 200 processed records. |
| Long-term memory | 4,000 characters by default; 1,000 characters per item. |
| Approved skills | Up to 100 skills; 8,000 characters per skill. |
| Scheduled jobs | Up to 100 active jobs and 200 terminal records. |
| Failed Telegram deliveries | Up to 100 failed replies; successful retries clear the stored text. |
| Recall index and quality counters | Approved memories and skills only; no unrestricted transcript content. |
| `runtime/feedback.jsonl` | Rotates at 1 MB and retains the current file plus one previous file. |
| `workspace/inbox/` | The 50 newest gateway-managed attachment files; gitignored and excluded from migration archives. |

The gateway does not duplicate full conversation transcripts and does not delete sessions created by other Codex projects or the Codex desktop app.

## Personal data migration

Create a versioned, checksummed archive:

```bash
PYTHONPATH=src python3 -m codex_codeshark export-data \
  "$HOME/codeshark-personal-data.codeshark.zip"
```

The archive includes memories, approved skills, their recall provenance and quality counters, task ratings, learning proposals, scheduled jobs, and administrator task metadata. It excludes the Telegram token, local configuration, Codex session files, enabled-group authorization, group request records, update offsets, failed-delivery payloads, attachments, and runtime logs. A migrated installation therefore starts with no enabled groups.

Archives are created with mode `0600` and may contain Telegram chat IDs and personal content. Keep them private and never commit them.

On a new Mac, clone the repository and run `setup` first. Then import:

```bash
PYTHONPATH=src python3 -m codex_codeshark import-data \
  "$HOME/codeshark-personal-data.codeshark.zip" --force
```

Queued one-time tasks are imported as cancelled, and active scheduled jobs are imported as paused. Review jobs with `/jobs` before resuming them.

## Troubleshooting

Start every diagnosis with:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

| Symptom | Resolution |
|---|---|
| Invalid bot token | Rerun `setup` and paste only the token shown by BotFather. |
| Telegram TLS verification failure | The client falls back to the verified macOS `/etc/ssl/cert.pem` bundle without disabling TLS verification. |
| MCP policy mismatch | Add every globally or profile-configured server to `mcp_policy.known_servers`. |
| Missing restricted profile | Rerun `setup` to create the `codex-codeshark` profile. |
| LaunchAgent is not running | Run `PYTHONPATH=src python3 -m codex_codeshark start`, then inspect `logs`. |
| Bot does not answer | Run `doctor`, confirm the LaunchAgent state, then check that the message came from the paired private chat. |
| Group mention is ignored | Confirm the administrator enabled the group, disable BotFather Privacy Mode, and send `@YourBotUsername REQUEST`. |

## Project layout

```text
Codex-codeshark/
├── assets/                  # Public project artwork
├── scripts/                 # macOS LaunchAgent management
├── src/codex_codeshark/     # Gateway, queue, policy, memory, and migration code
├── tests/                   # Offline standard-library unit tests
├── workspace/               # Only remote-writable project area
├── config.example.toml      # Public configuration schema
├── config.local.toml        # Private installation config, gitignored
└── runtime/                 # Private state, database, skills, feedback, and logs
```

The guest runtime lives separately under `~/Library/Application Support/Codex-codeshark/group/` so project and global `AGENTS.md`, memories, plugins, and custom skills are not inherited. Its `auth.json` is a symlink to the existing Codex login; credentials are not copied into the repository.

## Development

Create an isolated environment if desired, then install the local package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Run the offline test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run the live environment diagnostic separately:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

Tests never call Telegram or OpenAI networks. `doctor` intentionally checks the configured live installation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [CHANGELOG.md](CHANGELOG.md) for release notes.

## Upgrading

Stop the service, update the source tree, rerun the offline checks, and restart:

```bash
PYTHONPATH=src python3 -m codex_codeshark stop
git pull --ff-only
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m codex_codeshark doctor
PYTHONPATH=src python3 -m codex_codeshark start
```

SQLite schema additions are applied on startup. Personal data remains in `runtime/`; create an `export-data` archive before major upgrades.

Maintainers publish releases from a signed, GitHub-verified annotated tag whose name matches the versions in `pyproject.toml` and `src/codex_codeshark/__init__.py`:

```bash
python3 scripts/release_check.py --tag v0.1.0
git tag -s v0.1.0 -m "Codex-codeshark v0.1.0"
git push origin v0.1.0
```

The release workflow verifies the signature and version, runs the full test suite, builds source and wheel packages, and publishes them to GitHub Releases.

## Project status

Codex-codeshark is an early alpha with a deliberately narrow scope. The initial public-readiness milestones are implemented:

- [x] Hardened child process environment and explicit network policy.
- [x] First-class macOS service CLI and sanitized log inspection.
- [x] Telegram rate-limit handling and bounded failed-delivery recovery.
- [x] Searchable cross-session recall with provenance.
- [x] Usage counters, memory review, and feedback-aware skill ranking.
- [x] Safe Telegram document and image intake confined to `workspace/`.
- [x] Administrator-enabled Telegram groups with isolated natural-language mention execution.
- [x] Administrator development access to server-configured delegated project roots.
- [x] Signed-tag validation, packaged release artifacts, and upgrade guidance.

Additional administrator accounts, additional messaging channels, and multi-agent orchestration are not current goals.

## Contributing

Bug reports and focused improvements are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) before opening a pull request. For sensitive security issues, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.

## License

Codex-codeshark is released under the [MIT License](LICENSE).

The mascot artwork in `assets/codeshark-mascot.png` is distributed as part of this project under the same license by the repository owner.
