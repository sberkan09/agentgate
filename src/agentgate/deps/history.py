"""Co-change history from ``git log``."""

from __future__ import annotations

from collections import Counter

from ..git import Repo

MAX_COMMIT_FILES = 100  # bulk commits (reformatting, renames) say nothing about coupling


def cochange(repo: Repo, changed: list[str], window: int, min_count: int = 2) -> dict[str, str] | None:
    """Files that changed in >= ``min_count`` of the last ``window`` commits together with a changed file.

    Returns ``{co-changed file: changed file}`` or None when git log is unavailable.
    """
    proc = repo.run("log", "-n", str(window), "--name-only", "--format=%x00%H", check=False)
    if proc.returncode != 0:
        return None
    wanted = set(changed)
    counts: dict[str, Counter[str]] = {c: Counter() for c in wanted}
    for chunk in proc.stdout.split("\x00"):
        files = {ln for ln in chunk.splitlines()[1:] if ln}
        if not files or len(files) > MAX_COMMIT_FILES:
            continue
        for c in files & wanted:
            counts[c].update(files - {c})
    out: dict[str, str] = {}
    for c in sorted(counts):
        for other, n in sorted(counts[c].items()):
            if n >= min_count and other not in wanted:
                out.setdefault(other, c)
    return out
