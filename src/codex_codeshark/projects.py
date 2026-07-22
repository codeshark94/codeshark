from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECT = "General"
GLOBAL_SCOPE = "global"

_PROJECT_SYSTEM_DIRECTORIES = frozenset({
    "build",
    "deliverables",
    "inbox",
    "node_modules",
    "outputs",
    "tmp",
})
_PROJECT_MARKERS = (
    ".git",
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "main.tex",
)


@dataclass(frozen=True)
class WorkspaceProject:
    """A safely discovered project directory available to the administrator."""

    name: str
    path: Path


def discover_workspace_projects(
    workdir: Path,
    delegated_roots: tuple[Path, ...],
    *,
    agent_repository_root: Path | None = None,
    limit: int = 48,
) -> tuple[WorkspaceProject, ...]:
    """Discover project roots without recursively scanning administrator data.

    Direct children of the writable workspace are user projects unless they are
    Codeshark-managed/system directories. Delegated roots are inspected only
    two levels deep and only directories with a conventional project marker are
    considered. This keeps project routing bounded and server-controlled.
    """

    root = workdir.expanduser().resolve()
    agent_root = agent_repository_root.expanduser().resolve() if agent_repository_root else None
    discovered: dict[Path, WorkspaceProject] = {}

    def add(path: Path, name: str, *, workspace_project: bool = False) -> None:
        if len(discovered) >= limit:
            return
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved == root or not resolved.is_dir():
            return
        if agent_root is not None and not workspace_project:
            try:
                resolved.relative_to(agent_root)
            except ValueError:
                pass
            else:
                return
        try:
            normalized = normalize_project_name(name)
        except ValueError:
            return
        discovered.setdefault(resolved, WorkspaceProject(normalized, resolved))

    try:
        workspace_children = sorted(root.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        workspace_children = []
    for child in workspace_children:
        if (
            child.name.startswith(".")
            or child.name in _PROJECT_SYSTEM_DIRECTORIES
            or not child.is_dir()
        ):
            continue
        add(child, child.name, workspace_project=True)

    for delegated_root in delegated_roots:
        try:
            delegated = delegated_root.expanduser().resolve()
            children = sorted(delegated.iterdir(), key=lambda path: path.name.casefold())
        except OSError:
            continue
        for parent in children:
            if parent.name.startswith(".") or not parent.is_dir():
                continue
            candidates = (parent,)
            try:
                candidates += tuple(
                    child
                    for child in sorted(parent.iterdir(), key=lambda path: path.name.casefold())
                    if not child.name.startswith(".") and child.is_dir()
                )
            except OSError:
                pass
            for candidate in candidates:
                if not any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
                    continue
                try:
                    relative = candidate.relative_to(delegated)
                except ValueError:
                    continue
                add(candidate, relative.as_posix())

    return tuple(sorted(discovered.values(), key=lambda item: item.name.casefold()))


def project_named_in_request(
    request: str,
    candidates: tuple[WorkspaceProject, ...],
) -> str | None:
    """Return an unambiguous project explicitly named by path or label."""

    request_path = request.replace("\\", "/")
    normalized_request = _normalize_project_text(request_path)
    matches: list[str] = []
    for candidate in candidates:
        absolute_path = candidate.path.as_posix()
        label = _normalize_project_text(candidate.name)
        basename = _normalize_project_text(candidate.path.name)
        if absolute_path in request_path or (
            label and _contains_project_label(normalized_request, label)
        ) or (
            basename and _contains_project_label(normalized_request, basename)
        ):
            matches.append(candidate.name)
    unique = tuple(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def _normalize_project_text(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).casefold().strip()


def _contains_project_label(text: str, label: str) -> bool:
    return bool(re.search(rf"(?:^|\s){re.escape(label)}(?:$|\s)", text))


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


def create_workspace_project(workdir: Path, name: str) -> WorkspaceProject:
    """Create one safe direct-child workspace project selected by Project Router."""
    normalized = normalize_project_name(name)
    if (
        normalized.casefold() == DEFAULT_PROJECT.casefold()
        or normalized.startswith(".")
        or normalized in _PROJECT_SYSTEM_DIRECTORIES
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ValueError("project name must be a non-system direct workspace folder name")
    root = workdir.expanduser().resolve()
    candidate = root / normalized
    if candidate.parent != root:
        raise ValueError("project must be created directly inside the configured workspace")
    if candidate.exists():
        if not candidate.is_dir():
            raise ValueError("project path already exists and is not a directory")
    else:
        candidate.mkdir(mode=0o700)
    return WorkspaceProject(normalized, candidate.resolve())
