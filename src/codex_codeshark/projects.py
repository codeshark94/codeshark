from __future__ import annotations


DEFAULT_PROJECT = "General"
GLOBAL_SCOPE = "global"


def normalize_project_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise ValueError("project name must not be empty")
    if len(name) > 80 or any(ord(character) < 32 for character in name):
        raise ValueError("project name must be a single line of at most 80 characters")
    if name.casefold() == GLOBAL_SCOPE:
        raise ValueError(f"{GLOBAL_SCOPE!r} is reserved for global records")
    return name


def normalize_scope(value: str) -> str:
    if " ".join(value.split()).casefold() == GLOBAL_SCOPE:
        return GLOBAL_SCOPE
    return normalize_project_name(value)
