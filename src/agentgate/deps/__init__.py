"""Per-language dependency adapters used by ``agentgate.select``.

Each adapter builds a *reverse* graph ``{file: {files that depend on it}}``; ``closure`` walks it.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable

Reader = Callable[[str], str]


def closure(rev: dict[str, set[str]], changed: Iterable[str]) -> dict[str, str]:
    """Everything that transitively depends on ``changed`` -> the changed file it was reached from.

    The changed files themselves are included (mapped to themselves).
    """
    out: dict[str, str] = {}
    queue: deque[str] = deque()
    for c in sorted(set(changed)):
        out[c] = c
        queue.append(c)
    while queue:
        cur = queue.popleft()
        for dep in sorted(rev.get(cur, ())):
            if dep not in out:
                out[dep] = out[cur]
                queue.append(dep)
    return out
