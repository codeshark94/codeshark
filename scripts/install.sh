#!/bin/sh
# One-command macOS installer. It deliberately leaves secret entry and Telegram
# pairing interactive so neither value can leak into shell history or logs.
set -eu

REPOSITORY_URL="https://github.com/Younghegalian/codeshark.git"
INSTALL_DIR="${CODESHARK_INSTALL_DIR:-$HOME/.codeshark}"
CODEX_BINARY="/Applications/Codex.app/Contents/Resources/codex"

fail() {
    printf '%s\n' "Codeshark install failed: $1" >&2
    exit 1
}

if [ "$(uname -s)" != "Darwin" ]; then
    fail "this installer supports macOS only"
fi

command -v git >/dev/null 2>&1 || fail "install Xcode Command Line Tools, then rerun"
command -v python3 >/dev/null 2>&1 || fail "install Python 3.11 or newer, then rerun"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    || fail "Python 3.11 or newer is required"

if [ ! -x "$CODEX_BINARY" ]; then
    fail "install Codex desktop in /Applications and sign in, then rerun"
fi

if [ -e "$INSTALL_DIR" ]; then
    if ! git -C "$INSTALL_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        fail "install directory already exists and is not a Git checkout: $INSTALL_DIR"
    fi
    if [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
        fail "install directory has local changes; update it manually before rerunning: $INSTALL_DIR"
    fi
    printf '%s\n' "Updating Codeshark in $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    printf '%s\n' "Installing Codeshark in $INSTALL_DIR"
    git clone "$REPOSITORY_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
run_codeshark() {
    PYTHONPATH=src python3 -m codex_codeshark "$@"
}

printf '%s\n' ""
printf '%s\n' "Enter the BotFather token when prompted. The input is hidden and stored only in macOS Keychain."
run_codeshark setup
run_codeshark doctor
run_codeshark start

printf '%s\n' ""
printf '%s\n' "Codeshark is running. Verify it with:"
printf '%s\n' "  cd $INSTALL_DIR && PYTHONPATH=src python3 -m codex_codeshark service-status"
