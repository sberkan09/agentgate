"""C/C++ adapter: ``#include`` graph, resolved by relative path, then suffix/basename (cheap, approximate)."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict

from . import Reader

EXTENSIONS = (".h", ".hpp", ".c", ".cc", ".cpp")
_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"\n]+)[>"]', re.MULTILINE)


def is_cpp(path: str) -> bool:
    return path.endswith(EXTENSIONS)


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.split("/")[:-1], b.split("/")[:-1], strict=False):
        if x != y:
            break
        n += 1
    return n


def build_reverse(read: Reader, files: list[str]) -> dict[str, set[str]]:
    """``files`` are repo-relative paths of C/C++ sources and headers; returns includee -> includers."""
    known = set(files)
    by_base: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_base[posixpath.basename(f)].append(f)

    def resolve(src: str, inc: str) -> list[str]:
        local = posixpath.normpath(posixpath.join(posixpath.dirname(src), inc))
        if local in known:
            return [local]
        norm = posixpath.normpath(inc)
        if norm in known:
            return [norm]
        cands = [p for p in by_base.get(posixpath.basename(norm), ()) if p == norm or p.endswith("/" + norm)]
        if len(cands) > 1:
            best = max(_common_prefix(src, c) for c in cands)
            cands = [c for c in cands if _common_prefix(src, c) == best]
        return cands

    rev: dict[str, set[str]] = defaultdict(set)
    for f in files:
        try:
            text = read(f)
        except OSError:
            continue
        for inc in set(_INCLUDE.findall(text)):
            for target in resolve(f, inc.strip()):
                if target != f:
                    rev[target].add(f)
    return rev
