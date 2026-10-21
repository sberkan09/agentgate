"""Conflict forecast between open agent branches, via ``git merge-tree --write-tree``.

Contract (implemented in task #3):

    forecast(repo, cfg, head=None, patterns=None) -> ConflictReport

- branches = every remote-tracking branch matching cfg.agent_branches (or ``patterns``), excluding the base;
  when ``head`` is given it is included even if it does not match, and only pairs with it are checked.
- Two questions are answered, both with ``git merge-tree --write-tree --name-only``:
  1. Does the branch conflict with the base as it stands today? (``base_conflicts``: the branch needs a
     rebase before anything else.) Computed as merge-tree(base, branch).
  2. Would two branches conflict with each other once both sit on top of the base? (``pairs``.) Computed
     between the *rebased previews*: the tree merge-tree(base, X) wrapped in a throwaway commit on the base,
     compared with ``--merge-base=base``. Comparing raw branches instead reports the base's own changes as
     conflicts whenever a branch is behind it, which is the common case with many agents.
  Files are the names printed after the tree line. Branches with no merge base, or merge-tree failures,
  go to ``errors``.
- ``merge_order``: a greedy order that merges the least-entangled branch first (fewest conflicting
  partners, ties by fewest changed files vs base).
- Must work on a shallow clone where the refs were fetched (``git fetch origin +refs/heads/claude/*:...``).
"""

from __future__ import annotations

from itertools import combinations

from .config import Config
from .git import GitError, Repo
from .report import ConflictPair, ConflictReport

DEFAULT_MAX_BRANCHES = 40


def _resolves(repo: Repo, ref: str) -> bool:
    try:
        repo.rev_parse(ref)
    except GitError:
        return False
    return True


def _discover(repo: Repo, cfg: Config, patterns: list[str]) -> list[str]:
    """Agent branches matching the patterns, minus the base and minus branches already merged into it.

    A merged-but-not-deleted branch is not open work: pairing it with live branches only produces noise.
    """
    exclude = {cfg.base_ref, cfg.base}
    base_known = _resolves(repo, cfg.base_ref)
    found: list[str] = []
    for pattern in patterns:
        for name in repo.branches(pattern, remote=cfg.remote):
            if name in exclude or name in found:
                continue
            if base_known and repo.is_ancestor(name, cfg.base_ref):
                continue
            found.append(name)
    return found


def _resolve_head(repo: Repo, cfg: Config, head: str, found: list[str]) -> str | None:
    """Maps ``head`` to the name used in ``found`` (or a resolvable ref), None if it resolves to nothing."""
    if head in found:
        return head
    if cfg.remote and f"{cfg.remote}/{head}" in found:
        return f"{cfg.remote}/{head}"
    if _resolves(repo, head):
        return head
    if cfg.remote and _resolves(repo, f"{cfg.remote}/{head}"):
        return f"{cfg.remote}/{head}"
    return None


def _merge_tree(repo: Repo, a: str, b: str, merge_base: str | None = None) -> tuple[int, str, list[str], str]:
    """Runs merge-tree; returns (rc, tree oid, conflicting files, detail). rc 0 clean, 1 conflicts."""
    args = ["merge-tree", "--write-tree", "--name-only"]
    if merge_base:
        args.append(f"--merge-base={merge_base}")
    proc = repo.run(*args, a, b, check=False)
    lines = proc.stdout.splitlines()
    tree = lines[0].strip() if lines else ""
    files: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            break
        if line not in files:
            files.append(line)
    return proc.returncode, tree, files, (proc.stderr.strip() or proc.stdout.strip())


def _preview_on_base(repo: Repo, base: str, branch: str, report: ConflictReport) -> str | None:
    """A throwaway commit holding ``branch`` merged onto ``base``; None when that merge itself conflicts.

    The commit is created with commit-tree and never referenced, so it is garbage-collected later.
    """
    try:
        repo.merge_base(base, branch)
    except GitError as exc:
        report.errors.append(f"{branch}: no merge base with {base} ({exc})")
        return None
    rc, tree, files, detail = _merge_tree(repo, base, branch)
    if rc == 1:
        report.base_conflicts.append(ConflictPair(a=branch, b=base, files=files, kind="base"))
        return None
    if rc != 0 or not tree:
        report.errors.append(f"{branch}: merge-tree with {base} failed ({rc}): {detail}")
        return None
    return repo.out("commit-tree", tree, "-p", base, "-m", f"agentgate preview of {branch}")


def _check_pair(
    repo: Repo, a: str, b: str, previews: dict[str, str], base: str, errors: list[str]
) -> ConflictPair | None:
    """Conflict between two branches as they would be on top of the base.

    Raw branches are compared only when no base is known at all; a branch that conflicts with the base
    is left out of the pairs (it has to rebase first, and the raw comparison would just repeat the
    base conflict).
    """
    if a in previews and b in previews:
        rc, _, files, detail = _merge_tree(repo, previews[a], previews[b], merge_base=base)
    elif previews or _resolves(repo, base):
        return None
    else:
        try:
            repo.merge_base(a, b)
        except GitError as exc:
            errors.append(f"{a} vs {b}: no merge base ({exc})")
            return None
        rc, _, files, detail = _merge_tree(repo, a, b)
    if rc == 0:
        return None
    if rc != 1:
        errors.append(f"{a} vs {b}: merge-tree failed ({rc}): {detail}")
        return None
    return ConflictPair(a=a, b=b, files=files, kind="content" if files else "unknown")


def _merge_order(repo: Repo, cfg: Config, branches: list[str], pairs: list[ConflictPair]) -> list[str]:
    partners: dict[str, set[str]] = {b: set() for b in branches}
    for p in pairs:
        partners[p.a].add(p.b)
        partners[p.b].add(p.a)
    size: dict[str, int] = {}
    for b in branches:
        try:
            size[b] = len(repo.changed_files(cfg.base_ref, b))
        except GitError:
            size[b] = 0
    remaining = list(branches)
    order: list[str] = []
    while remaining:
        pick = min(remaining, key=lambda b: (len(partners[b] & set(remaining)), size[b], b))
        order.append(pick)
        remaining.remove(pick)
    return order


def forecast(
    repo: Repo,
    cfg: Config,
    head: str | None = None,
    patterns: list[str] | None = None,
    max_branches: int = DEFAULT_MAX_BRANCHES,
) -> ConflictReport:
    report = ConflictReport(base=cfg.base_ref, head=head, branches=[], pairs=[])
    branches = _discover(repo, cfg, patterns or cfg.agent_branches)

    if head is not None:
        resolved = _resolve_head(repo, cfg, head, branches)
        if resolved is None:
            report.errors.append(f"head {head!r} does not resolve to a ref")
            report.branches = branches[:max_branches]
            return report
        head = resolved
        report.head = head
        if head not in branches:
            branches.append(head)

    if len(branches) > max_branches:
        report.errors.append(
            f"{len(branches)} branches exceed max_branches={max_branches}; truncated to {max_branches}"
        )
        kept = sorted(b for b in branches if b != head)[: max_branches - (1 if head else 0)]
        branches = ([head] if head else []) + kept
    report.branches = branches

    if head is not None:
        candidates = [(head, o) for o in branches if o != head]
    else:
        candidates = list(combinations(branches, 2))
    previews: dict[str, str] = {}
    if _resolves(repo, cfg.base_ref):
        for br in branches:
            commit = _preview_on_base(repo, cfg.base_ref, br, report)
            if commit:
                previews[br] = commit
    for a, b in candidates:
        pair = _check_pair(repo, a, b, previews, cfg.base_ref, report.errors)
        if pair is not None:
            report.pairs.append(pair)

    report.merge_order = _merge_order(repo, cfg, branches, report.pairs)
    return report
