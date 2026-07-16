# Codex-codeshark

Codex-codeshark is a private, single-user Telegram gateway for the local OpenAI Codex CLI on macOS. It turns a Telegram private chat into a durable control plane for one sandboxed Codex session, scheduled checks, approved long-term memory, and reusable local skills.

This project is designed for personal use. It is not a hosted bot service, a multi-user gateway, or a multi-agent framework.

## Highlights

- Continues one interactive Codex session across Telegram messages and restarts.
- Persists queued work in SQLite and executes one task at a time.
- Supports one-time reminders, heartbeat intervals, and five-field cron jobs.
- Runs scheduled work with `codex exec --ephemeral` so it does not create session history.
- Lets the model propose memories and skills, but never applies them without explicit approval.
- Loads at most three relevant approved skills for each request.
- Rotates oversized sessions after creating a reviewable durable-summary proposal.
- Requires explicit approval for requests that may modify external state.
- Applies a fail-closed MCP server and tool allowlist.
- Exports portable personal data without exporting tokens or machine-specific configuration.
- Uses only the Python standard library at runtime.

## Architecture

```text
Telegram private chat
        |
        v
Authenticated user + approval gate
        |
        v
Persistent SQLite queue and scheduler
        |
        v
CodexRunner -> local Codex CLI -> workspace/
        |
        +-> approved memory and relevant local skills
```

Telegram is only the authenticated transport and control plane. Codex performs reasoning and tool execution. Remote file operations are confined to the server-controlled `workspace/` directory by the `workspace-write` Codex sandbox.

## Requirements

- macOS
- Python 3.11 or newer
- The Codex desktop app installed at `/Applications/Codex.app`
- An existing Codex login (`codex login status` must succeed)
- A Telegram bot token created with [BotFather](https://t.me/BotFather)

## Quick start

```bash
git clone https://github.com/Younghegalian/codeshark.git Codex-codeshark
cd Codex-codeshark
PYTHONPATH=src python3 -m codex_codeshark setup
```

Setup asks for the BotFather token using hidden input. Paste only the token, not the BotFather message or a shell command. The token is written to macOS Keychain and is never stored in the repository.

Setup then prints a one-time message such as:

```text
/pair A1B2C3D4
```

Send that exact message to the new bot in a private Telegram chat within three minutes. Pairing records exactly one allowed Telegram user ID.

Validate the installation:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

A healthy installation reports `PASS` for local configuration, Keychain token access, Telegram API access, Codex login, the restricted Codex profile, and the MCP policy.

Run in the foreground first:

```bash
PYTHONPATH=src python3 -m codex_codeshark run
```

After verifying the bot in Telegram, stop the foreground process and install the LaunchAgent:

```bash
PYTHONPATH=src python3 scripts/install_launch_agent.py
```

Check the background service and logs:

```bash
launchctl print gui/$(id -u)/com.codeshark.agent
tail -f runtime/agent.out.log runtime/agent.err.log
```

Remove the LaunchAgent:

```bash
python3 scripts/uninstall_launch_agent.py
```

## Local configuration

`setup` creates a gitignored `config.local.toml`. It contains installation-specific values:

- The paired Telegram user ID
- The fixed workspace path
- The Codex binary and profile
- Polling, task timeout, and queue limits
- Session and memory capacity limits
- The MCP server inventory and per-server tool allowlist

It does not contain the BotFather token or conversation transcripts. It is still private because it contains a user ID and local filesystem paths.

See [`config.example.toml`](config.example.toml) for the complete schema.

## Telegram commands

| Command | Purpose |
|---|---|
| Plain text | Queue a task in the current interactive Codex session |
| `/status` | Show active work, queue depth, session capacity, and stored item counts |
| `/tasks` | List recent persistent task records |
| `/cancel` | Cancel the active Codex process or the oldest queued task |
| `/new` | Permanently delete the current Codex session and start fresh |
| `/remember TEXT` | Store an explicitly approved long-term memory |
| `/memories` | List approved long-term memories |
| `/forget ID` | Delete a long-term memory |
| `/learn memory TEXT` | Create a memory proposal |
| `/learn skill NAME \| PROCEDURE` | Create a reusable skill proposal |
| `/learning` | List pending learning proposals |
| `/approve ID` | Approve a learning proposal, risky task, or risky scheduled job |
| `/reject ID` | Reject a pending proposal, task, or job |
| `/skills` | List approved local skills |
| `/forget_skill ID` | Delete an approved skill |
| `/good [NOTE]` | Positively rate the last successful task |
| `/bad [REASON]` | Negatively rate the last successful task |
| `/remind MINUTES REQUEST` | Run a request once after a delay |
| `/heartbeat MINUTES REQUEST` | Run a periodic check |
| `/cron EXPRESSION \| REQUEST` | Run a request on a local-time five-field cron schedule |
| `/jobs` | List scheduled jobs |
| `/pause ID` | Pause a scheduled job |
| `/resume_job ID` | Resume a paused job |
| `/delete_job ID` | Delete a scheduled job |
| `/mcp` | Show the effective MCP server and tool policy |
| `/help` | Show the command summary |

## Learning model

Codex may append a hidden structured proposal when a task reveals a durable preference, fact, or reusable procedure. The gateway removes that block from the Telegram response and stores it as pending.

Nothing is learned automatically:

1. The model or user proposes a memory or skill.
2. The proposal appears under `/learning`.
3. The user applies it with `/approve ID` or discards it with `/reject ID`.

Approved memories are injected as durable context. Approved skills are selected by relevance and loaded only when needed. Approving a skill with the same name replaces the existing procedure instead of creating an unbounded series of copies.

## Sessions and scheduling

Interactive Telegram requests continue the current persisted Codex session. The session ID and turn count are stored in `runtime/state.json`.

When the configured turn limit is reached, Codex creates a durable-summary proposal. The gateway deletes the previous Codex session only after that proposal is safely staged. If summarization or deletion fails, the existing session is kept.

Scheduled jobs are always ephemeral. They do not create or continue Codex sessions. A recurring job cannot enqueue another run while its previous run is still active, preventing an unbounded backlog.

## Security model

Security-sensitive defaults are part of the application contract:

- Exactly one Telegram user ID is allowed.
- Group chats and unauthorized users are ignored.
- The Telegram token is stored in macOS Keychain.
- The token is removed from the environment before Codex starts.
- The workspace path is server-controlled and never accepted from Telegram.
- The Codex profile must use `sandbox_mode = "workspace-write"` and `approval_policy = "never"`.
- Only one Codex task runs at a time, with cancellation and a configurable timeout.
- External-state and destructive requests are held for explicit approval.
- An approved task interrupted during execution requires approval again after restart.
- Every configured MCP server must appear in the local policy.
- Servers without an explicit tool allowlist are disabled for this gateway.

The risk classifier and injected execution policy are defense-in-depth controls, not a substitute for a minimal MCP allowlist or operating-system isolation. Do not expose this bot to untrusted users or the public internet as a shared service.

### MCP policy example

```toml
[mcp_policy]
known_servers = ["github", "docs"]

[mcp_policy.allowed_tools]
docs = ["search", "fetch"]
# github is known but disabled for this gateway
```

At setup time, MCP server names found in the global Codex configuration and the `codex-codeshark` profile are copied into `known_servers`. No MCP tools are enabled automatically. If the Codex MCP inventory changes later, update `config.local.toml`; startup fails closed when the inventory and policy do not match.

## Data retention

| Store | Retention policy |
|---|---|
| `runtime/state.json` | Current session ID, turn count, and Telegram update offset only |
| Interactive Codex session | Deleted and rotated at `max_session_turns` after staging a summary proposal |
| Scheduled Codex runs | Ephemeral; no Codex session is stored |
| Task records in `runtime/agent.db` | Raw prompts are cleared on completion, failure, cancellation, or rejection; 200 terminal records are retained |
| Learning proposals | Up to 100 pending proposals and 200 processed records |
| Long-term memory | 4,000 characters by default; 1,000 characters per item |
| Approved skills | Up to 100 skills; 8,000 characters per skill |
| Scheduled jobs | Up to 100 active jobs and 200 terminal records |
| `runtime/feedback.jsonl` | Rotates at 1 MB and retains the current file plus one previous file |

The gateway does not duplicate full conversation transcripts. It does not delete sessions created by other Codex projects or the Codex desktop app.

## Personal data migration

Create a versioned, checksummed personal-data archive:

```bash
PYTHONPATH=src python3 -m codex_codeshark export-data \
  "$HOME/codeshark-personal-data.codeshark.zip"
```

The archive contains:

- Long-term memories
- Approved skills
- Task ratings
- Learning proposals
- Scheduled jobs and terminal task metadata

It excludes:

- The Telegram bot token
- `config.local.toml`
- Codex session files
- `runtime/state.json`
- Runtime logs

Archives are created with mode `0600` and may contain Telegram chat IDs and personal content. Keep them private and never commit them. `*.codeshark.zip` is gitignored.

On a new Mac, clone the project and run `setup` first so the new machine has its own Keychain token and local paths. Then import:

```bash
PYTHONPATH=src python3 -m codex_codeshark import-data \
  "$HOME/codeshark-personal-data.codeshark.zip" --force
```

To prevent duplicate side effects, queued one-time tasks are imported as cancelled and active scheduled jobs are imported as paused. Review them with `/jobs` and resume only the jobs you still want.

## Troubleshooting

Start with:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

Common setup failures:

- **Invalid bot token:** rerun `setup` and paste only the token shown by BotFather. Hidden input does not echo characters.
- **Telegram TLS verification failure:** Python.org builds may not have a default CA file. Codex-codeshark falls back to the verified macOS `/etc/ssl/cert.pem` bundle without disabling TLS verification.
- **MCP policy mismatch:** ensure every server configured globally or in the project Codex profile appears under `mcp_policy.known_servers`.
- **Missing profile:** rerun `setup`. It creates a restricted `codex-codeshark` profile when one does not already exist.

## Development

Run the full offline test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests do not call Telegram or OpenAI networks. Before handing off a change, run both the test suite and `doctor`.

The project intentionally has no runtime dependencies beyond Python's standard library.
