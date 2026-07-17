<div align="center">
  <img src="assets/codeshark-mascot.png" alt="Codex-codeshark mascot" width="300">
  <h1>Codex-codeshark</h1>
  <p><strong>Your Codex agent, on call from anywhere.</strong></p>
  <p>
    Hand off repo work, investigations, and recurring checks.<br>
    CodeShark runs on your Mac, learns how you work, and returns the finished result.
  </p>
  <p>
    <a href="https://github.com/Younghegalian/codeshark/actions/workflows/tests.yml"><img src="https://github.com/Younghegalian/codeshark/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
    <a href="https://www.apple.com/macos/"><img src="https://img.shields.io/badge/platform-macOS-000000?logo=apple&amp;logoColor=white" alt="macOS"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="MIT License"></a>
    <a href="pyproject.toml"><img src="https://img.shields.io/badge/runtime_dependencies-0-2ea44f" alt="Zero runtime dependencies"></a>
  </p>
  <p>
    <a href="#quick-start">Quick start</a> ·
    <a href="#what-it-can-do">Capabilities</a> ·
    <a href="#security-defaults">Security</a> ·
    <a href="docs/telegram.md">Chat interface</a> ·
    <a href="#development">Development</a>
  </p>
</div>

Codex-codeshark turns the OpenAI Codex CLI already installed on your Mac into a persistent personal agent. Give it an outcome, not a sequence of button clicks: it can inspect and modify approved projects, run commands, work from attached files, keep context across tasks, and follow up later on a schedule.

Telegram is the current remote inbox, not the product itself. The reasoning, tools, project access, memory, and automation live in the local agent runtime.

> [!IMPORTANT]
> Codex-codeshark is deliberately built for one administrator on one Mac. It is not a hosted bot service, a shared shell, or a multi-agent framework.

## What it can do

| Capability | What you get |
|---|---|
| Project work | Inspect, edit, test, and diagnose code inside a private workspace or explicitly delegated project roots. |
| Persistent context | Continue the same Codex session across requests and process restarts without re-explaining the project every time. |
| Durable memory | Recall useful preferences and project conventions, then load only the relevant memories and skills for the current task. |
| Scheduled follow-through | Run one-time reminders, heartbeat checks, and cron jobs in clean ephemeral sessions. |
| File-based investigation | Accept photos and documents as task context through a size-limited private inbox. |
| Guarded execution | Keep unapproved work read-only and require explicit approval before mutation or external side effects. |
| Isolated group analysis | Let mentioned group members research and create sandbox-only analysis files without exposing private projects, tools, or administrator context. |
| Service-grade operation | Persist queued work, recover interrupted tasks, retry failed result delivery, rotate bounded data, and expose diagnostics and logs. |

The useful unit is a finished task:

```text
Fix the failing authentication tests in my API project and summarize the diff.
Read this error log, find the root cause, and tell me the smallest safe fix.
Every weekday at 09:00, check whether the local service is healthy.
Remember that this repo uses conventional commits and never squashes migrations.
```

It uses your existing Codex login, needs no separate model API key, and adds zero runtime dependencies.

## How it works

```text
Natural-language request or file
              |
              v
     Durable queue + risk gate
              |
              v
   Persistent or ephemeral Codex run
              |
       +------+------------------+
       |                         |
       v                         v
Approved local projects   Memory, skills, schedules,
and allowlisted tools     feedback, and bounded state
       |                         |
       +------------+------------+
                    v
              Final result
```

Interactive work continues a persisted Codex thread. Scheduled work runs ephemerally so background checks do not pollute that conversation. The queue executes one task at a time and survives service restarts.

## Quick start

### Requirements

- macOS
- Python 3.11 or newer
- [Codex desktop](https://openai.com/codex/) with Codex CLI 0.138.0 or newer
- An active Codex login
- A bot token created with [BotFather](https://t.me/BotFather)

### 1. Clone

```bash
git clone https://github.com/Younghegalian/codeshark.git Codex-codeshark
cd Codex-codeshark
```

### 2. Configure the agent

```bash
PYTHONPATH=src python3 -m codex_codeshark setup
```

The guided setup verifies Codex, stores the bot token in macOS Keychain, pairs one administrator, creates the isolated runtime profiles, and writes the private local configuration.

See the [chat interface guide](docs/telegram.md) for pairing, commands, optional group access, and delivery troubleshooting.

### 3. Verify and start

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
PYTHONPATH=src python3 -m codex_codeshark start
PYTHONPATH=src python3 -m codex_codeshark service-status
```

Use foreground mode for the first test if you prefer:

```bash
PYTHONPATH=src python3 -m codex_codeshark run
```

Service operations use the same CLI:

```bash
PYTHONPATH=src python3 -m codex_codeshark logs --lines 100
PYTHONPATH=src python3 -m codex_codeshark restart
PYTHONPATH=src python3 -m codex_codeshark stop
```

## Memory that compounds

After a successful private task, the agent can identify a durable preference, working pattern, project fact, or reusable procedure. Approved memories become searchable context; approved skills are selected by relevance and loaded only when needed.

Automatic learning is evidence-bound. An exact, non-secret statement from the current administrator request may be applied immediately. Inferred or transformed candidates remain pending for review. One-off details, speculation, credentials, and unnecessary sensitive data are excluded.

Stable names update existing records rather than creating unbounded duplicates. Usage and explicit positive or negative feedback help rank equally relevant knowledge. Guest and scheduled runs never feed the learning loop.

## Security defaults

Connecting an agent to local projects deserves a small, inspectable trust boundary:

- Exactly one paired administrator receives the same memory, tools, and control commands in private chat or an enabled group. Each administrator chat retains its own persistent Codex session.
- Non-administrator group requests are ephemeral, MCP-disabled, and confined to a separate sandbox; they may perform ordinary network research and create or modify only sandbox files.
- Administrator mutations and external work wait for explicit approval; non-administrator writes are limited to the isolated group sandbox.
- Project roots are fixed in local configuration and can never be supplied by a remote request.
- The child process receives a strict environment allowlist; parent credentials and SSH-agent sockets are not forwarded.
- Network access is disabled by default and set explicitly for every run.
- MCP servers and tools are disabled unless represented in the local allowlist; inventory mismatches fail closed.
- Attachments are size-limited, privately stored, and confined to the agent inbox.
- Non-administrator group requests use a separate Codex home, an ephemeral session, no personal context or tools, and a workspace cleared after each run.
- Queues, sessions, memories, skills, feedback, schedules, attachments, and failed deliveries all have retention bounds.
- The background service runs a private versioned source snapshot instead of importing executable code from a delegated project tree.

See [SECURITY.md](SECURITY.md) for the full threat boundary, credential handling, and vulnerability reporting policy.

## Configuration and tool policy

`setup` writes a gitignored `config.local.toml`. Remote requests cannot change its paths or execution policy.

Delegate one or more local project roots:

```toml
delegated_roots = ["/Users/yourname/workspace"]
```

Keep read-only inspection roots separate:

```toml
read_only_roots = ["/Users/yourname/Documents/reference"]
```

MCP access is allowlist-based:

```toml
[mcp_policy]
known_servers = ["github", "docs"]

[mcp_policy.allowed_tools]
docs = ["search", "fetch"]
# github is known but disabled
```

Startup fails when the live MCP inventory and local policy do not match. No server or tool is enabled automatically. See [config.example.toml](config.example.toml) for the full schema.

### Administrator full access

The secure default keeps unapproved private work read-only. Set the following only when the paired administrator deliberately wants the bot to act as a full local delegate:

```toml
admin_full_access = true
```

In this mode, the paired administrator's tasks use Codex `danger-full-access` with no approval pause in private chat and administrator-enabled groups. The agent can create files outside delegated roots, use live network access, install Codex plugins, and enable configured MCP servers. Other group members remain mention-only, ephemeral, MCP-disabled, and confined to the separate group sandbox. Do not enable this mode for a shared account or a bot exposed to untrusted private users.

## Bounded state and migration

The agent stores only what it needs to resume useful work:

| Store | Bound |
|---|---|
| Interactive session | Rotated at `max_session_turns` after a durable summary proposal is persisted. |
| Scheduled and guest runs | Ephemeral; their Codex sessions are not retained. |
| Task history | Raw prompts are cleared at terminal status; 200 terminal records remain. |
| Long-term memory | 12,000 characters by default, with 1,000 characters per item. |
| Skills | At most 100 approved skills, up to 8,000 characters each. |
| Scheduled jobs | At most 100 active jobs and 200 terminal records. |
| Attachments | The 50 newest gateway-managed files. |
| Feedback | Rotates at 1 MB and retains one previous file. |

Export portable personal data before moving machines or performing a major upgrade:

```bash
PYTHONPATH=src python3 -m codex_codeshark export-data \
  "$HOME/codeshark-personal-data.codeshark.zip"
```

Import it after cloning and running `setup` on the new Mac:

```bash
PYTHONPATH=src python3 -m codex_codeshark import-data \
  "$HOME/codeshark-personal-data.codeshark.zip" --force
```

Archives are versioned, checksummed, created with mode `0600`, and exclude tokens, local configuration, Codex session files, runtime logs, attachments, and guest authorization. They still contain personal content and local paths, so keep them private.

## Project layout

```text
Codex-codeshark/
├── assets/                  # Project artwork
├── docs/                    # Interface and operational guides
├── scripts/                 # macOS service helpers
├── src/codex_codeshark/     # Queue, runtime, policy, memory, and migration
├── tests/                   # Offline standard-library unit tests
├── workspace/               # Private agent workspace and inbox
├── config.example.toml      # Public configuration schema
├── config.local.toml        # Private installation config, gitignored
└── runtime/                 # Private state, database, skills, and logs
```

## Development

Create an isolated environment if desired:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Run the offline test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run the live installation diagnostic separately:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

Tests never call messaging or OpenAI networks. `doctor` intentionally verifies the configured live installation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [CHANGELOG.md](CHANGELOG.md) for release notes.

## Upgrading

Stop the service, update the source, run the checks, and start it again:

```bash
PYTHONPATH=src python3 -m codex_codeshark stop
git pull --ff-only
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m codex_codeshark doctor
PYTHONPATH=src python3 -m codex_codeshark start
```

Restarting deploys a fresh private source snapshot. SQLite schema additions are applied automatically and personal data remains in `runtime/`.

## Project status

Codex-codeshark is an early alpha with a deliberately narrow scope. The core personal-agent path is implemented:

- [x] Persistent sessions, bounded rotation, and durable task recovery
- [x] Delegated local project work with capability approval
- [x] Scheduled ephemeral jobs and overlap protection
- [x] Evidence-bound automatic learning and searchable recall
- [x] Feedback-aware skill ranking and memory review
- [x] Private attachment intake and failed-result recovery
- [x] Isolated, read-only guest conversations
- [x] First-class macOS service management and diagnostics
- [x] Signed release checks and portable personal-data migration

Additional administrators, additional messaging channels, and multi-agent orchestration are not current goals.

## Contributing

Bug reports and focused improvements are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) before opening a pull request. For sensitive security issues, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.

## License

Codex-codeshark is released under the [MIT License](LICENSE).

The mascot artwork in `assets/codeshark-mascot.png` is distributed as part of this project under the same license by the repository owner.
