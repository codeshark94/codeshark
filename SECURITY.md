# Security Policy

Codex-codeshark connects Telegram input to a local agent runtime. Security reports are taken seriously, especially when they involve authentication bypass, secret exposure, workspace escape, approval bypass, unsafe migration archives, or unintended external side effects.

## Supported versions

| Version | Supported |
|---|---|
| Latest commit on `main` | Yes |
| Older commits or forks | No |

Until the first stable release, security fixes are made on `main` only.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting or a private security advisory for this repository. Include:

- The affected commit or version
- Preconditions and configuration
- Reproduction steps or a minimal proof of concept
- Expected and actual behavior
- Potential impact
- Any suggested mitigation

Do not include real Telegram tokens, Codex credentials, personal data, or unrelated secrets. Replace them with clearly marked test values.

## Security boundaries

The intended boundaries are:

- One explicitly paired Telegram user in a private chat
- A server-controlled `workspace/` directory
- A restricted Codex profile using `workspace-write`
- A mandatory MCP server inventory and per-tool allowlist
- Explicit approval for requests classified as destructive or externally mutating
- Bot tokens stored in macOS Keychain and a strict Codex child-environment allowlist
- Outbound Codex network access disabled by default and explicitly configured per child
- Size-limited Telegram attachments stored only in the server-controlled workspace

The risk classifier and model instructions are defense-in-depth controls. They do not replace operating-system isolation or careful credential and MCP policy management.

The Codex child receives only basic process, locale, temporary-directory, certificate, and Codex-home variables. Parent API keys, Telegram credentials, cloud credentials, and SSH-agent sockets are not forwarded. Credential-bearing MCP tools remain a separate trust boundary and should stay disabled unless required.
