# Changelog

All notable changes to Codex-codeshark are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow [Semantic Versioning](https://semver.org/) from its first tagged release.

## Unreleased

### Added

- Public repository documentation, security policy, contribution guide, issue templates, and macOS CI.
- Official Codex-codeshark mascot asset.
- MIT License.
- Quiet task delivery with approval, error, and final-result messages only.
- Telegram rate-limit handling and a bounded failed-delivery retry queue.
- Strict Codex child-environment allowlist and explicit outbound network policy.
- Service CLI for start, stop, restart, status, and sanitized log inspection.
- Searchable approved-memory and skill recall with provenance and quality counters.
- Usage tracking, stale-memory review, and feedback-aware skill ranking.
- Size-limited Telegram photo and document intake under `workspace/inbox/`.
- Signed-tag validation, version checks, package builds, and GitHub release automation.
- Complete source-distribution manifest and per-user data root for installed packages.
- Administrator-enabled Telegram groups with mention-triggered, natural-language, ephemeral guest requests.
- Separate guest Codex home and least-privilege filesystem permission profile with network, MCP, personal context, and writes disabled.
- Server-configured delegated project roots for administrator development work.
- Separate private/group Telegram command scopes and non-migrating group authorization.
- Effective Codex model reporting in `/status` and `doctor`.
- Requester-scoped group conversation continuity with six-exchange bounds, 30-day expiry, disable-time deletion, and migration exclusion.
- Model-initiated automatic learning that proactively creates or updates durable administrator memories and reusable skills, with audit and deletion controls.
- Bot-specific `gpt-5.5` model pinning for private and isolated group tasks.

## 0.1.0 - 2026-07-16

### Added

- Single-user Telegram pairing and private-chat authorization.
- Persistent Codex session continuity and bounded session rotation.
- SQLite-backed task queue, reminders, heartbeat jobs, and cron schedules.
- Approval gates for learning proposals and risky requests.
- Approved long-term memories and relevant reusable skills.
- MCP server and tool allowlist enforcement.
- Portable personal-data export and import.
- macOS Keychain token storage and LaunchAgent support.
- Offline unit test suite and live `doctor` diagnostic.
