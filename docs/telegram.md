# Telegram interface guide

Telegram is Codex-codeshark's authenticated remote inbox. The agent itself runs locally through the Codex CLI; this document covers only setup, commands, group access, and delivery troubleshooting for the chat interface.

## Setup and pairing

Create a bot with [BotFather](https://t.me/BotFather), then run:

```bash
PYTHONPATH=src python3 -m codex_codeshark setup
```

The guided setup:

1. Verifies the existing Codex login.
2. Accepts the BotFather token through hidden input.
3. Stores the token in macOS Keychain.
4. Displays a one-time command such as `/pair A1B2C3D4`.
5. Accepts that command from one private chat within three minutes.
6. Creates the local administrator profile and isolated group runtime.
7. Registers separate command menus for private and group chats.

Paste only the token at the hidden prompt. Do not paste the full BotFather message or a shell command.

Run the live diagnostic after pairing:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

## Private-chat commands

Plain text queues a task in the current interactive Codex session. A photo or document is stored under the private, gitignored `workspace/inbox/` directory and its caption becomes the task instruction.

On the first plain-text request, Codeshark asks once how it should address its owner. That explicit preference is kept as a pinned owner profile in private administrator tasks; other durable preferences are learned only from explicit, useful interaction. Codeshark never asks to store credentials, secrets, payment data, or unnecessary sensitive information. To introduce the owner in groups, set a separate explicit public card; private owner context is never shared there.

To receive a generated or existing result file, ask naturally (for example, `작업한 결과파일 보여줘`, `PDF 보내줘`, or `send the report file`). The agent may attach a regular file only from a configured workspace or project root. Use `/send PATH` when you already know the path.

### Sessions and tasks

| Command | Purpose |
|---|---|
| Plain text | Queue work in the current Codex session; receive only the final result. |
| Photo or document | Store the attachment privately and queue its caption as the task. |
| `/status` | Show active work, queue depth, session capacity, model, and stored item counts. |
| `/tasks` | List recent persistent task records. |
| `/cancel` | Cancel the active process or the oldest queued task. |
| `/new` | Delete the current Codex session and start fresh. |
| `/name NAME` | Change Codeshark's self-introduction name. This does not change the Telegram bot's display name. |
| `/owner_public TEXT` | Set the owner information Codeshark may share naturally in group introductions. Use `clear` to remove it. |

### Memory, skills, and feedback

| Command | Purpose |
|---|---|
| `/remember TEXT` | Store a long-term memory. |
| `/memories` | List learned memories. |
| `/forget ID` | Delete a memory. |
| `/recall QUERY` | Search approved memories and skills with provenance. |
| `/review_memories` | List unused, stale, or negatively rated memories. |
| `/learn memory TEXT` | Add or update a memory immediately. |
| `/learn skill NAME \| PROCEDURE` | Add or update a reusable skill immediately. |
| `/learning` | Audit recent automatic-learning events and pending proposals. |
| `/skills` | List approved skills. |
| `/forget_skill ID` | Delete an approved skill. |
| `/good [NOTE]` | Positively rate the last successful task. |
| `/bad [REASON]` | Negatively rate the last successful task. |

### Approvals and automation

| Command | Purpose |
|---|---|
| `/approve ID` | Approve a pending task, scheduled job, or learning proposal. |
| `/reject ID` | Reject a pending item. |
| `/remind MINUTES REQUEST` | Run a request once after a delay. |
| `/heartbeat MINUTES REQUEST` | Run a periodic check. |
| `/cron EXPRESSION \| REQUEST` | Run a request on a local-time five-field cron schedule. |
| `/jobs` | List scheduled jobs. |
| `/pause ID` | Pause a scheduled job. |
| `/resume_job ID` | Resume a paused job. |
| `/delete_job ID` | Delete a scheduled job. |
| `/mcp` | Show the effective MCP server and tool policy. |
| `/help` | Show the command summary. |

### Delivery recovery

| Command | Purpose |
|---|---|
| `/deliveries` | List final replies that failed or had ambiguous delivery. |
| `/retry_delivery ID` | Retry one failed reply and purge its stored text after success. |

## Optional group access

Group access is disabled by default. Only the paired administrator can enable it. In an enabled group, the administrator retains the same capabilities and approval flow as in a private chat, while each private or group chat keeps an independent persistent Codex session. Other group members receive an isolated ephemeral agent with no access to administrator sessions, memories, skills, projects, attachments, credentials, or configured roots. They may perform ordinary network research and can inspect, create, or modify files only in the separate group sandbox; that sandbox is cleared after every request. MCP tools, dependency or plugin installation, destructive changes, policy/root changes, and external state-changing work remain unavailable to non-administrators.

For natural-language mentions, disable Privacy Mode for the bot with BotFather's `/setprivacy` command. Telegram does not deliver ordinary mention messages to privacy-enabled bots. Codex-codeshark still discards every received group message that does not explicitly mention the bot username.

Add the bot to a group, then send:

```text
/enable_group@YourBotUsername
@YourBotUsername Explain what a Python context manager does
```

Each non-administrator member's six newest successful exchanges are retained only for that member in that group and expire after 30 days. Disabling a group deletes its participant context. Administrator commands from an enabled group have the same effect as their private-chat equivalents.

| Command | Who can use it | Purpose |
|---|---|---|
| `/enable_group` | Paired administrator, in the group | Enable mention requests. |
| `/disable_group` | Paired administrator, in the group | Revoke access immediately. |
| `/group_status` | Paired administrator, in the group | Show whether the group is enabled. |
| `@BotUsername REQUEST` | Paired administrator | Continue the persistent Codex session for this chat with the same approval requirements and capabilities. |
| `@BotUsername REQUEST` | Other member of an enabled group | Run an ephemeral network-capable analysis in the isolated group sandbox. |
| `/groups` | Paired administrator, private chat or enabled group | List enabled groups. |
| `/disable_group CHAT_ID` | Paired administrator, private chat or enabled group | Revoke a group remotely. |

If you prefer Telegram not to deliver ordinary group messages to the bot process at all, keep Privacy Mode enabled and do not use group mention mode.

## Troubleshooting

Start with:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
PYTHONPATH=src python3 -m codex_codeshark service-status
PYTHONPATH=src python3 -m codex_codeshark logs --lines 100
```

| Symptom | Resolution |
|---|---|
| Invalid bot token | Rerun `setup` and paste only the token shown by BotFather. |
| TLS verification failure | The client uses the verified macOS `/etc/ssl/cert.pem` fallback without disabling verification. |
| Bot does not answer | Confirm the service is running and the message came from the paired private chat. |
| Group mention is ignored | Confirm the group is enabled, Privacy Mode is disabled, and the message contains `@YourBotUsername`. |
| Final result did not arrive | Check `/deliveries`, then use `/retry_delivery ID`. |

The bot token must never be committed, logged, printed, or passed to Codex. It remains in macOS Keychain and is excluded from the Codex child environment.
