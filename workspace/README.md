# Agent workspace

Codex file operations requested through Telegram are confined to this directory by default.

Telegram photos and documents are stored under `inbox/` with private file permissions. The
directory is intentionally ignored by Git and is not included in personal-data exports. The
gateway keeps at most its 50 newest generated attachment files.
