"""Thin wrappers around the git CLI. Every git call in agentgate goes through here."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Repo:
    root: Path

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            check=False,
            text=True,
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
        return proc

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def rev_parse(self, ref: str) -> str:
        return self.out("rev-parse", "--verify", f"{ref}^{{commit}}")

    def merge_base(self, a: str, b: str) -> str:
        return self.out("merge-base", a, b)

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return self.run("merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0

    def changed_files(self, base: str, head: str = "HEAD", include_untracked: bool = False) -> list[str]:
        """Files changed between merge-base(base, head) and head, sorted and unique."""
        mb = self.merge_base(base, head)
        files = set(self.out("diff", "--name-only", mb, head).splitlines())
        if include_untracked:
            files.update(self.out("ls-files", "--others", "--exclude-standard").splitlines())
        return sorted(f for f in files if f)

    def branches(self, pattern: str, remote: str | None = "origin") -> list[str]:
        """Branch refs matching a glob such as ``claude/*``; remote-tracking refs when ``remote`` is set."""
        prefix = f"refs/remotes/{remote}/" if remote else "refs/heads/"
        out = self.out("for-each-ref", "--format=%(refname)", f"{prefix}{pattern}")
        return [
            line[len("refs/") :] if not remote else line[len("refs/remotes/") :] for line in out.splitlines()
        ]

    def ls_files(self, *pathspecs: str) -> list[str]:
        return (
            self.out("ls-files", "--", *pathspecs).splitlines()
            if pathspecs
            else self.out("ls-files").splitlines()
        )

    def read_file(self, path: str, ref: str | None = None) -> str:
        if ref is None:
            return (self.root / path).read_text(errors="replace")
        return self.run("show", f"{ref}:{path}").stdout


def find_repo(start: Path | None = None) -> Repo:
    start = (start or Path.cwd()).resolve()
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise GitError(f"not a git repository: {start}")
    return Repo(Path(proc.stdout.strip()))
