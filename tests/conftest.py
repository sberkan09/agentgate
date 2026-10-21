"""Shared fixtures: a throwaway git repository with a base branch and helper to add agent branches."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentgate.git import Repo


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Sandbox:
    def __init__(self, root: Path):
        self.root = root
        self.repo = Repo(root)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        git(root, "config", "commit.gpgsign", "false")

    def write(self, path: str, content: str) -> None:
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def commit(self, msg: str, files: dict[str, str] | None = None) -> str:
        for path, content in (files or {}).items():
            self.write(path, content)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)
        return git(self.root, "rev-parse", "HEAD")

    def branch(self, name: str, from_ref: str = "main") -> None:
        git(self.root, "checkout", "-q", "-b", name, from_ref)

    def checkout(self, name: str) -> None:
        git(self.root, "checkout", "-q", name)

    def as_remote_tracking(self, remote: str = "origin") -> None:
        """Mirror local branches as refs/remotes/<remote>/* so code paths that read remote refs work."""
        for line in git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines():
            git(self.root, "update-ref", f"refs/remotes/{remote}/{line}", line)


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    root = tmp_path / "repo"
    root.mkdir()
    sb = Sandbox(root)
    sb.commit("init", {"README.md": "# demo\n"})
    return sb
