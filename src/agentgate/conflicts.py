"""Conflict forecast between open agent branches, via ``git merge-tree --write-tree``.

Contract (implemented in task #3):

    forecast(repo, cfg, head=None, patterns=None) -> ConflictReport

- branches = every remote-tracking branch matching cfg.agent_branches (or ``patterns``), excluding the base;
  when ``head`` is given it is included even if it does not match, and only pairs with it are checked.
- A pair conflicts when ``git merge-tree --write-tree --name-only A B`` exits 1; the files are the names
  printed after the tree line. Branches with no merge base, or merge-tree failures, go to ``errors``.
- ``merge_order``: a greedy order that merges the least-entangled branch first (fewest conflicting
  partners, ties by fewest changed files vs base).
- Must work on a shallow clone where the refs were fetched (``git fetch origin +refs/heads/claude/*:...``).
"""

from __future__ import annotations

from .config import Config
from .git import Repo
from .report import ConflictReport


def forecast(
    repo: Repo, cfg: Config, head: str | None = None, patterns: list[str] | None = None
) -> ConflictReport:
    raise NotImplementedError("task #3")
