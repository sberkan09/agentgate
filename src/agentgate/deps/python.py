"""Python adapter: import graph via ``ast``, module names mapped onto files by dotted-path suffix."""

from __future__ import annotations

import ast
import posixpath
from collections import defaultdict

from . import Reader


def is_python(path: str) -> bool:
    return path.endswith(".py")


def build_reverse(read: Reader, files: list[str]) -> dict[str, set[str]]:
    """``files`` are repo-relative ``.py`` paths; returns imported file -> importing files."""
    known = set(files)
    by_module: dict[str, set[str]] = defaultdict(set)
    for f in files:
        parts = f[: -len(".py")].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for i in range(len(parts)):
            if parts[i:]:
                by_module[".".join(parts[i:])].add(f)

    def rel(base_dir: str, mod: str) -> list[str]:
        p = posixpath.normpath(posixpath.join(base_dir, mod.replace(".", "/"))) if mod else base_dir
        return [c for c in (p + ".py", p + "/__init__.py") if c in known]

    rev: dict[str, set[str]] = defaultdict(set)
    for f in files:
        try:
            tree = ast.parse(read(f))
        except (OSError, SyntaxError, ValueError):
            continue
        targets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    targets |= by_module.get(a.name, set())
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = posixpath.dirname(f)
                    for _ in range(node.level - 1):
                        base = posixpath.dirname(base)
                    mod = node.module or ""
                    targets.update(rel(base, mod))
                    for a in node.names:
                        targets.update(rel(base, f"{mod}.{a.name}" if mod else a.name))
                else:
                    mod = node.module or ""
                    targets |= by_module.get(mod, set())
                    for a in node.names:
                        targets |= by_module.get(f"{mod}.{a.name}", set())
        for t in targets:
            if t != f:
                rev[t].add(f)
    return rev
