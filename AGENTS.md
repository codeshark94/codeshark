# Codex-codeshark

## Purpose

This repository is a private Telegram gateway for the local Codex CLI. The model provider is OpenAI through the existing ChatGPT login and the `codex-codeshark` Codex profile. Do not add Ollama or copy authentication tokens into the repository.

## Architecture

- Telegram is only the authenticated transport and control plane.
- `CodexRunner` is the agent runtime adapter.
- A persisted Codex thread provides conversational continuity.
- Remote file operations are confined to `workspace/` by the Codex `workspace-write` sandbox.
- Only explicitly paired Telegram user IDs are authorized.

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
- Keep the workspace path server-controlled; never accept an arbitrary filesystem path from Telegram.
- Keep the user allowlist mandatory and private-chat-only.
- Preserve cancellation, timeouts, single-worker execution, and Telegram message chunking.
- Keep dependencies at zero unless a dependency solves a demonstrated problem.
- Tests must not call Telegram or OpenAI networks.
