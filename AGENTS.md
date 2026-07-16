# Codex-codeshark

## Purpose

This repository is a private Telegram gateway for the local Codex CLI. The model provider is OpenAI through the existing ChatGPT login and the `codex-codeshark` Codex profile. Do not add Ollama or copy authentication tokens into the repository.

## Architecture

- Telegram is only the authenticated transport and control plane.
- `CodexRunner` is the agent runtime adapter.
- A persisted Codex thread provides conversational continuity.
- File writes are confined to `workspace/` by the Codex `workspace-write` sandbox.
- Administrator tasks may inspect read-only roots and work in server-configured delegated roots.
- One explicitly paired Telegram user is the administrator.
- Group access must be enabled by that administrator and remains read-only, ephemeral, and isolated from administrator data.

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
- Keep the administrator allowlist mandatory and keep privileged controls private-chat-only.
- Keep group requests administrator-enabled, explicit-mention-only, read-only, ephemeral, MCP-disabled, and isolated from private memory and sessions.
- Preserve cancellation, timeouts, single-worker execution, and Telegram message chunking.
- Keep dependencies at zero unless a dependency solves a demonstrated problem.
- Tests must not call Telegram or OpenAI networks.
