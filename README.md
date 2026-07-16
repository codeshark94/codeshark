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
    <a href="#roadmap">Roadmap</a>
  </p>
</div>

Codex-codeshark connects one authenticated Telegram private chat to one sandboxed Codex session on your Mac. It keeps work queued across restarts, runs scheduled checks, proposes durable memories and reusable skills, and gives you explicit approval gates before risky actions.

It uses your existing Codex login. The project does not require a separate model API key, does not copy ChatGPT credentials into the repository, and stores the Telegram bot token in macOS Keychain.

> [!IMPORTANT]
> Codex-codeshark is intentionally a **single-user, Telegram-only, macOS gateway**. It is not a hosted bot service, a multi-user platform, or a multi-agent framework.

## Why Codex-codeshark?

Open-ended agent frameworks are powerful, but a personal coding gateway benefits from a smaller and more inspectable security boundary. Codex-codeshark focuses on one channel, one user, one workspace, and one local Codex runtime.

| Principle | What it means here |
|---|---|
| Local first | Codex runs on your Mac inside a server-controlled workspace. |
| Single user | Exactly one paired Telegram user ID is accepted. |
| Approval gated | Learning and risky external actions wait for explicit approval. |
| Durable, not unbounded | Queues, sessions, memories, skills, feedback, and logs have retention limits. |
| Fail closed | Unlisted MCP servers or tools prevent startup instead of silently becoming available. |
| Portable personal data | Memories, skills, feedback, and schedules can move without exporting secrets. |

## What it does

- **Persistent conversation** — continues one Codex thread across Telegram messages and process restarts.
- **Durable task queue** — stores queued work in SQLite and executes exactly one task at a time.
- **Scheduled work** — supports one-time reminders, heartbeat intervals, and five-field cron expressions.
- **Ephemeral automation** — scheduled jobs use `codex exec --ephemeral` and do not create conversation history.
- **Approval-gated learning** — lets Codex propose long-term memories and reusable skills without silently applying them.
- **Relevant skill loading** — injects at most three approved skills selected for the current request.
- **Bounded sessions** — summarizes durable context for review, deletes the full session, and starts fresh at the configured turn limit.
- **Risk approval** — holds destructive or external-state requests until `/approve` is received.
- **MCP policy** — disables every server and tool that is not explicitly allowed for this gateway.
- **Portable migration** — exports personal data in a versioned, checksummed archive without tokens or local configuration.
- **Zero runtime dependencies** — uses only the Python standard library at runtime.

## Quick start

### Requirements

- macOS
- Python 3.11 or newer
- [Codex desktop](https://openai.com/codex/) installed at `/Applications/Codex.app`
- An active Codex login
- A Telegram bot token created with [BotFather](https://t.me/BotFather)

### 1. Clone

```bash
git clone https://github.com/Younghegalian/codeshark.git Codex-codeshark
cd Codex-codeshark
```

Codex-codeshark is currently installed from source; it is not published to PyPI.

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
6. Creates the local configuration and restricted Codex profile.
7. Registers the English Telegram command menu.

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
- Restricted Codex profile
- MCP allowlist consistency

### 4. Run it

Foreground mode is useful for the first test:

```bash
PYTHONPATH=src python3 -m codex_codeshark run
```

Send `/status` to the bot, then stop the foreground process with `Ctrl+C`.

For an always-on gateway, install the macOS LaunchAgent:

```bash
PYTHONPATH=src python3 scripts/install_launch_agent.py
```

Verify the service:

```bash
launchctl print gui/$(id -u)/com.codeshark.agent
tail -f runtime/agent.out.log runtime/agent.err.log
```

Remove the service:

```bash
python3 scripts/uninstall_launch_agent.py
```

## Security defaults

Codex-codeshark connects an agent runtime to a real messaging surface. Treat every inbound message as untrusted until the pairing and policy checks have accepted it.

- Exactly one Telegram user ID is allowed.
- Group chats and unauthorized users are ignored.
- The BotFather token is stored in macOS Keychain, not in project files.
- The Telegram token is removed from the environment before Codex starts.
- Telegram cannot choose the workspace path or pass arbitrary Codex CLI flags.
- Codex runs with `sandbox_mode = "workspace-write"` and `approval_policy = "never"`.
- Only one Codex task runs at a time, with cancellation and a configurable timeout.
- Requests classified as destructive or externally mutating wait for explicit approval.
- Interrupted approved tasks require approval again after restart.
- Every configured MCP server must be represented in the gateway policy.
- Servers without an explicit tool allowlist are disabled.

The text classifier and injected execution policy are defense-in-depth controls, not a perfect security boundary. Keep credential-bearing MCP tools disabled unless they are required, and do not expose this bot as a shared public service.

When started manually, the Codex child process inherits the gateway's environment except for `TELEGRAM_BOT_TOKEN`. Run the gateway with a minimal environment and do not export unrelated credentials into it. A stricter child-environment allowlist is planned before the first stable release.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and the supported-version policy.

## How it works

```text
Telegram private chat
        |
        v
User allowlist + private-chat check
        |
        v
Risk and approval gate
        |
        v
Persistent SQLite queue + scheduler
        |
        v
Memory and relevant approved skills
        |
        v
CodexRunner -> local Codex CLI -> workspace/
        |
        +-> Telegram response
```

Telegram is the authenticated transport and control plane. Codex performs reasoning and tool execution. Remote file operations are confined to the repository's `workspace/` directory by the restricted Codex profile.

## Telegram command reference

### Sessions and tasks

| Command | Purpose |
|---|---|
| Plain text | Queue a task in the current interactive Codex session. |
| `/status` | Show active work, queue depth, session capacity, and stored item counts. |
| `/tasks` | List recent persistent task records. |
| `/cancel` | Cancel the active Codex process or the oldest queued task. |
| `/new` | Permanently delete the current Codex session and start fresh. |

### Memory, skills, and feedback

| Command | Purpose |
|---|---|
| `/remember TEXT` | Store an explicitly approved long-term memory. |
| `/memories` | List approved long-term memories. |
| `/forget ID` | Delete a long-term memory. |
| `/learn memory TEXT` | Create a memory proposal. |
| `/learn skill NAME \| PROCEDURE` | Create a reusable skill proposal. |
| `/learning` | List pending learning proposals. |
| `/approve ID` | Approve a learning proposal, risky task, or risky scheduled job. |
| `/reject ID` | Reject a pending proposal, task, or job. |
| `/skills` | List approved local skills. |
| `/forget_skill ID` | Delete an approved skill. |
| `/good [NOTE]` | Positively rate the last successful task. |
| `/bad [REASON]` | Negatively rate the last successful task. |

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

Approved memories become durable context. Approved skills are selected by keyword relevance and loaded only when needed. Approving a skill with an existing name replaces its procedure instead of creating an unbounded set of copies.

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
- The MCP server inventory and per-server tool allowlist

It does not contain the BotFather token or conversation transcripts. It is still private because it includes a Telegram user ID and local filesystem paths.

See [config.example.toml](config.example.toml) for the complete schema.

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
| Task records in `runtime/agent.db` | Raw prompts are cleared on terminal status; 200 terminal records are retained. |
| Learning proposals | Up to 100 pending proposals and 200 processed records. |
| Long-term memory | 4,000 characters by default; 1,000 characters per item. |
| Approved skills | Up to 100 skills; 8,000 characters per skill. |
| Scheduled jobs | Up to 100 active jobs and 200 terminal records. |
| `runtime/feedback.jsonl` | Rotates at 1 MB and retains the current file plus one previous file. |

The gateway does not duplicate full conversation transcripts and does not delete sessions created by other Codex projects or the Codex desktop app.

## Personal data migration

Create a versioned, checksummed archive:

```bash
PYTHONPATH=src python3 -m codex_codeshark export-data \
  "$HOME/codeshark-personal-data.codeshark.zip"
```

The archive includes memories, approved skills, task ratings, learning proposals, scheduled jobs, and terminal task metadata. It excludes the Telegram token, local configuration, Codex session files, update offsets, and runtime logs.

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
| LaunchAgent is not running | Reinstall it and inspect `runtime/agent.err.log`. |
| Bot does not answer | Run `doctor`, confirm the LaunchAgent state, then check that the message came from the paired private chat. |

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

## Roadmap

Codex-codeshark is an early alpha with a deliberately narrow scope. The highest-value remaining work is:

- [ ] Hardened child process boundary: explicit environment allowlist and documented network policy.
- [ ] First-class service CLI: `start`, `stop`, `restart`, `service-status`, and safe log inspection.
- [ ] Telegram delivery resilience: rate-limit handling, bounded retries, and clearer failed-delivery state.
- [ ] Searchable cross-session recall with provenance, without retaining unrestricted transcripts.
- [ ] Better learning quality: usage counters, stale-memory review, and feedback-driven skill ranking.
- [ ] Safe Telegram document and image intake confined to `workspace/`.
- [ ] Release automation: version checks, signed tags, packaged artifacts, and upgrade guidance.

Multi-user operation, additional messaging channels, and multi-agent orchestration are not current goals.

## Contributing

Bug reports and focused improvements are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) before opening a pull request. For sensitive security issues, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.

## License

Codex-codeshark is released under the [MIT License](LICENSE).

The mascot artwork in `assets/codeshark-mascot.png` is distributed as part of this project under the same license by the repository owner.
