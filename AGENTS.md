# Codex-codeshark

## Purpose

This repository runs Codeshark, a local Codex agent with Telegram as its authenticated remote interface. The model provider is OpenAI through the existing ChatGPT login and the `codex-codeshark` Codex profile. Do not add Ollama or copy authentication tokens into the repository.

## Architecture

- Telegram provides authenticated remote conversation and control.
- `CodexRunner` is the agent runtime adapter.
- A persisted Codex thread provides conversational continuity per administrator chat.
- File writes are confined to `workspace/` by the Codex `workspace-write` sandbox.
- Administrator tasks may inspect read-only roots, work in server-configured delegated roots, and inspect Codeshark's own server-controlled repository.
- One explicitly paired Telegram user is the administrator.
- Group access must be enabled by that administrator and is direct-address-only: an explicit mention, a reply to a Codeshark message, or a reply within an already addressed Codeshark conversation chain.
- An administrator's authenticated identity, capabilities, and approval state carry into an enabled group. Maintain an independent persistent Codex session per administrator chat so private and group conversation context do not leak across chat boundaries.
- Non-administrator group requests are ephemeral and isolated from administrator data, memories, sessions, credentials, and delegated/read-only roots. They may perform ordinary network research and exploration and may create or modify files only inside the server-configured group sandbox. Destructive changes, credential or identity access, policy/root changes, dependency or plugin installation, deployment or production control, and external state-changing actions remain administrator-only.

## Commands

Run all checks before handing off a change:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m codex_codeshark doctor
```

Run the bot locally:

```bash
PYTHONPATH=src python3 -m codex_codeshark run
```

## Change rules

- Never log, print, commit, or send the Telegram bot token to Codex.
- Keep writable, delegated, and read-only root paths server-controlled; never accept a new filesystem root from Telegram.
- Keep the administrator allowlist mandatory. An administrator retains the same authorized capabilities and approval requirements in a private chat or an administrator-enabled group; do not make privileged controls private-chat-only solely because of chat type.
- Keep group requests administrator-enabled and direct-address-only: an explicit mention, a reply to a Codeshark message, or a reply within an already addressed Codeshark conversation chain. Non-administrator requests must remain ephemeral, MCP-disabled, and isolated from administrator memory, sessions, credentials, and configured project roots; permit only ordinary network research/exploration and writes confined to the server-configured group sandbox.
- Preserve cancellation, timeouts, per-session serialization, the three-worker execution limit, and Telegram message chunking.
- Keep dependencies at zero unless a dependency solves a demonstrated problem.
- Tests must not call Telegram or OpenAI networks.
