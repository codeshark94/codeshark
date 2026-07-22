# Telegram interface guide

Telegram is Codex-codeshark's authenticated remote chat interface. This guide covers setup, commands, group access, and delivery troubleshooting for that interface; the local Codex runtime provides the agent's reasoning, tools, memory, and project access.

## Setup and pairing

Create a bot with [BotFather](https://t.me/BotFather), then run:

```bash
PYTHONPATH=src python3 -m codex_codeshark setup
```

For a fresh installation, the one-command installer runs this setup, `doctor`, and the background service in sequence:

```bash
curl -fsSL https://raw.githubusercontent.com/codeshark94/codeshark/main/scripts/install.sh | sh
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

Plain text queues a task in the active project's interactive Codex session. Use `/project NAME` to create or switch a project context; sessions, long-term memories, and assistant assets do not cross project boundaries. If a private-chat task in that same project is already running, a safe follow-up message is injected into that active Codex turn, so instructions such as "also check the failing test" keep the same working context instead of creating another queue item. A follow-up that independently requires approval remains a separate approval-gated task. A photo or document is stored under the private, gitignored `workspace/.codeshark/inbox/` directory and its caption becomes the task instruction. Up to three independent tasks may run in parallel, while tasks in the same persistent chat remain ordered to protect that chat's session.

On the first plain-text request, Codeshark asks once how it should address its owner. That explicit preference is kept as a pinned owner profile in private administrator tasks; other durable preferences are learned only from explicit, useful interaction. Codeshark never asks to store credentials, secrets, payment data, or unnecessary sensitive information. To introduce the owner in groups, set a separate explicit public card; private owner context is never shared there.

To receive a generated or existing result file, ask naturally (for example, `작업한 결과파일 보여줘`, `PDF 보내줘`, or `send the report file`). The final user-facing agent—not an intermediate review or routing step—decides whether attachments are needed and selects the directly relevant final artifact set. It may send one file or multiple files when the completed result needs them; it does not dump co-located sources or supporting files. A request for a concrete final deliverable such as `완성본을 만들어줘` attaches the matching final file in the same response when one is available. Use `/file_delivery on` to attach newly produced manuscripts, reports, documents, and figure results automatically in this chat. Code, test, and source-file edits remain a text summary unless you explicitly ask for a file. The agent may attach a regular file only from a configured workspace or project root. Use `/send PATH` when you already know the path.

For substantive code, analysis, research, document, report, or artifact work, Codeshark uses independent cross-validation by default: a primary phase in the current project session, a separate read-only validator session with no primary-session history, then a reconciliation phase back in the primary session. The validation memo is internal handoff material: the final response is the corrected result, not an un-applied review report. Simple factual questions and standalone external side-effect actions skip the extra pass. On installations that require approval for file changes, approve a writable task before its primary phase can make changes.

Manuscript authoring and revision receive a stricter bounded loop: a low-cost plan, source/PDF/figure/typography audit by the author, an independent editorial gate, and up to two correction-and-recheck cycles. The gate checks journal-facing structure and abstract, generated-looking meta prose and repetitive caveats, notation and units, composite-figure consistency and normalization, captions, and page-by-page PDF readability. It uses any supplied journal brief for task-specific requirements and returns the corrected manuscript rather than its internal review memo.

For existing figures, charts, images, and multipanel academic layouts, Codeshark selects a visual-layout routine. It inventories source aspect ratios and crop constraints, uses a consistent grid and uniform scaling, renders the final page, and visually inspects it before delivery. It does not stretch images or silently crop scientific content to make a layout fit.

A concrete figure-edit instruction (for example, a Fig./panel/SEM/marker/legend/caption change) is treated as a revision, not a request to approve the current output. Codeshark must locate the exact source, regenerate and inspect a new relevant artifact, and attach it. Without a newly changed safe artifact, the task remains unfinished rather than returning a “no issues” verdict.

### Sessions and tasks

| Command | Purpose |
|---|---|
| Plain text | Queue work in the current Codex session, or steer the active private task when safe; receive only the final result. |
| Photo or document | Store the attachment privately and queue its caption as the task. |
| `/status` | Show active work, queue depth, session capacity, model, and stored item counts. |
| `/tasks` | List recent persistent task records. |
| `/task ID` | Show the task's routing tier, phase, acceptance checks, artifacts, and delivery state. |
| `/guardrails` | Show regression-rule candidates created from explicit negative feedback. |
| `/cancel` | Cancel the active process or the oldest queued task. |
| `/file_delivery on\|off` | Automatically attach newly produced manuscript, report, document, and figure results, or turn that behavior off. |
| `/project [NAME]` | Show or switch the active project. Projects start empty and default to `General`. |
| `/new`, `/clear_temp` | Delete only the active project's temporary Codex session and start fresh; long-term memories remain. |
| `/name NAME` | Change Codeshark's self-introduction name. This does not change the Telegram bot's display name. |
| `/owner_public TEXT` | Set the owner information Codeshark may share naturally in group introductions. Use `clear` to remove it. |

### Memory, skills, and feedback

| Command | Purpose |
|---|---|
| `/remember TEXT` | Store a long-term memory in the active project. |
| `/memories` | List the active project's memories and global identity records. |
| `/forget ID` | Delete a memory visible in the active project. |
| `/recall QUERY` | Search approved memories and skills with provenance. |
| `/save KIND \| TITLE \| CONTENT` | Store a structured assistant asset in the active project (`project`, `person`, `commitment`, `decision`, `preference`, or `knowledge`). |
| `/vault [QUERY]` | List relevant assistant assets from the active project. |
| `/forget_asset ID` | Delete one assistant asset. |
| `/review_memories` | List unused, stale, or negatively rated memories. |
| `/learn memory TEXT` | Add or update a memory immediately. |
| `/learn skill NAME \| PROCEDURE` | Add or update a reusable skill immediately. |
| `/learning` | Audit recent automatic-learning events and pending proposals. |
| `/skills` | List approved skills. |
| `/forget_skill ID` | Delete an approved skill. |
| `/good [NOTE]` | Positively rate the last successful task. |
| `/bad [REASON]` | Negatively rate the last successful task. |

Assistant assets are private administrator context. They are selected only when relevant to a private administrator task and never enter group prompts.

## Personal vault migration

The same ChatGPT/OpenAI login authenticates Codex, but it is not used as a Codeshark data store. To move private memories, skills, and assistant assets automatically between Macs, configure the same user-controlled private sync folder locally on each machine, push from the source, then pull on the new Mac before starting the service. See the [migration instructions](../README.md#bounded-state-and-migration). Chat messages cannot configure this folder.

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

Group access is disabled by default. Only the paired administrator can enable it. In an enabled group, the administrator retains the same capabilities and approval flow as in a private chat, while each private or group chat keeps an independent persistent Codex session. Other group members receive an isolated ephemeral agent with no access to administrator sessions, memories, skills, projects, attachments, credentials, or configured roots. They may perform ordinary network research and can inspect, create, or modify files only in the separate group sandbox. When **Attach result files from the group sandbox** is enabled in Security Settings, Codeshark can attach only a safe result file created by the current request to that same group before the sandbox is cleared. MCP tools, dependency or plugin installation, destructive changes, policy/root changes, and external state-changing work remain unavailable to non-administrators.

For natural-language mentions, disable Privacy Mode for the bot with BotFather's `/setprivacy` command. Telegram does not deliver ordinary mention messages to privacy-enabled bots. Codeshark accepts only direct group requests: an explicit bot mention, a reply to one of its own messages, or a reply within an already addressed Codeshark conversation chain. Its final response is threaded as a reply to the request message.

Add the bot to a group, then send:

```text
/enable_group@YourBotUsername
@YourBotUsername Explain what a Python context manager does
Reply in a Codeshark conversation: Explain what a Python context manager does
```

The 12 newest messages and successful Codeshark exchanges that Telegram delivers from a group are shared as context only within that group and expire after 30 days. Ordinary group messages are context only, never execution requests. Requests in one group are handled in order so that context does not race. This does not include messages Telegram does not deliver to the bot. Disabling a group deletes its group context. Administrator commands from an enabled group have the same effect as their private-chat equivalents.

| Command | Who can use it | Purpose |
|---|---|---|
| `/enable_group` | Paired administrator, in the group | Enable direct group requests. |
| `/disable_group` | Paired administrator, in the group | Revoke access immediately. |
| `/group_status` | Paired administrator, in the group | Show whether the group is enabled. |
| `@BotUsername REQUEST` or reply in a Codeshark conversation | Paired administrator | Continue the persistent Codex session for this chat with the same approval requirements and capabilities. |
| `@BotUsername REQUEST` or reply in a Codeshark conversation | Other member of an enabled group | Run an ephemeral network-capable analysis in the isolated group sandbox. |
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
| Group request is ignored | Confirm the group is enabled and the message either mentions `@YourBotUsername`, replies to a Codeshark message, or replies within an already addressed Codeshark conversation. Disable Privacy Mode for natural-language mentions. |
| Final result did not arrive | Check `/deliveries`, then use `/retry_delivery ID`. |

The bot token must never be committed, logged, printed, or passed to Codex. It remains in macOS Keychain and is excluded from the Codex child environment.
