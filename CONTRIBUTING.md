# Contributing to Codex-codeshark

Thank you for helping improve Codex-codeshark. The project intentionally stays small: one authenticated Telegram user, one local Codex runtime, one server-controlled workspace, and no runtime dependencies outside the Python standard library.

Participation is governed by the project's [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Use a GitHub issue for bugs or feature proposals that change behavior.
- Keep changes focused on the reported problem.
- Do not add providers, channels, or dependencies without a demonstrated need.
- Never include Telegram tokens, Codex credentials, personal data, local paths, or files from `runtime/`.
- Report vulnerabilities through the process in [SECURITY.md](SECURITY.md), not a public issue.

## Development setup

```bash
git clone https://github.com/Younghegalian/codeshark.git Codex-codeshark
cd Codex-codeshark
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The runtime has no third-party dependencies. The editable install is only for a convenient local command.

## Required checks

Run the complete offline suite before submitting a change:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
```

If you have a configured private installation, also run:

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
```

`doctor` contacts Telegram and inspects the local Codex installation, so it is not part of CI.

## Pull requests

A useful pull request includes:

- A concise description of the problem and user impact
- The smallest change that solves it
- Tests for new or corrected behavior
- Documentation updates when commands, configuration, security, or retention changes
- No unrelated formatting or refactoring

By contributing, you agree that your contribution is licensed under the MIT License.
