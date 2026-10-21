"""CMake target graph: source file -> targets -> dependents -> tests.

Why the include graph is not enough: a change to ``src/engine/physics2d/src/world2d.cpp`` is included by
nobody, so the include closure is empty, yet every test that links ``mce_physics2d`` observes it. This
adapter reads the link graph from the CMake sources, without configuring the project.

It understands, per CMakeLists.txt (comments stripped):

- ``add_library(<t> [STATIC|SHARED|MODULE|INTERFACE|OBJECT] [ALIAS <x>] <sources...>)``
- ``add_executable(<t> <sources...>)``
- ``target_link_libraries(<t> [PUBLIC|PRIVATE|INTERFACE] <deps...>)``
- ``add_test(NAME <n> COMMAND <t> ...)`` / ``add_test(<n> <t> ...)``
- project macros whose name contains ``add_library``, ``add_executable`` or ``add_test`` and take
  keyword lists ``SOURCES``, ``DEPS``, ``PUBLIC_DEPS``, ``PRIVATE_DEPS`` (CMake's cmake_parse_arguments
  convention): ``mce_add_test(test_physics2d SOURCES a.cpp DEPS mce::mce_physics2d)``.
- ``set(<var> <values...>)`` and ``list(APPEND <var> <values...>)`` in the same file, so
  ``${_sources}`` expands; ``${PROJECT_SOURCE_DIR}/x`` becomes ``x``; other ``${...}`` are dropped.

Namespaced deps (``mce::mce_core``) map to the bare target name. A dependency that is not a known
target (``Threads::Threads``, ``box2d::box2d``) is ignored.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import Reader

_CALL = re.compile(r"(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(")
_KEYWORDS = {
    "SOURCES",
    "DEPS",
    "PUBLIC_DEPS",
    "PRIVATE_DEPS",
    "PUBLIC",
    "PRIVATE",
    "INTERFACE",
    "NAME",
    "COMMAND",
}
_TYPES = {
    "STATIC",
    "SHARED",
    "MODULE",
    "INTERFACE",
    "OBJECT",
    "ALIAS",
    "IMPORTED",
    "GLOBAL",
    "EXCLUDE_FROM_ALL",
}
_SRC_EXT = (".cpp", ".cc", ".cxx", ".c", ".m", ".mm", ".h", ".hpp")


@dataclass
class Target:
    name: str
    sources: set[str] = field(default_factory=set)  # repo-relative
    deps: set[str] = field(default_factory=set)  # bare target names
    is_test: bool = False


@dataclass
class CMakeGraph:
    targets: dict[str, Target]
    tests: dict[str, str]  # ctest name -> target name (or itself when the command is unknown)

    def _dependents(self) -> dict[str, set[str]]:
        rev: dict[str, set[str]] = defaultdict(set)
        for t in self.targets.values():
            for d in t.deps:
                if d in self.targets:
                    rev[d].add(t.name)
        return rev

    def tests_for_files(self, files: list[str]) -> dict[str, str]:
        """ctest names affected by the given source files, mapped to the file that affects them."""
        by_source: dict[str, list[str]] = defaultdict(list)
        for t in self.targets.values():
            for s in t.sources:
                by_source[s].append(t.name)
        rev = self._dependents()
        target_tests: dict[str, list[str]] = defaultdict(list)
        for test, target in self.tests.items():
            target_tests[target].append(test)
        out: dict[str, str] = {}
        for f in files:
            seen: set[str] = set()
            stack = list(by_source.get(f, ()))
            while stack:
                t = stack.pop()
                if t in seen:
                    continue
                seen.add(t)
                for test in target_tests.get(t, ()):
                    out.setdefault(test, f)
                stack.extend(rev.get(t, ()))
        return out


def _args(text: str, open_paren: int) -> tuple[str, int]:
    depth, i = 0, open_paren
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i], i + 1
        i += 1
    return text[open_paren + 1 :], len(text)


def _tokens(args: str) -> list[str]:
    return [t.strip("\"'") for t in re.split(r"\s+", args.strip()) if t.strip("\"'")]


def _expand(tok: str, variables: dict[str, list[str]]) -> list[str]:
    m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", tok)
    if m:
        return list(variables.get(m.group(1), []))
    # A repo-root-relative path keeps a "//" marker so _rel does not join it onto the CMakeLists' dir.
    tok = re.sub(r"^\$\{(PROJECT_SOURCE_DIR|CMAKE_SOURCE_DIR)\}/?", "//", tok)
    tok = re.sub(r"^\$\{CMAKE_CURRENT_SOURCE_DIR\}/?", "", tok)
    return [] if "$" in tok else [tok]


def _bare(dep: str) -> str:
    return dep.split("::")[-1]


def parse_graph(read: Reader, files: list[str]) -> CMakeGraph:
    targets: dict[str, Target] = {}
    tests: dict[str, str] = {}
    pending_links: list[tuple[str, list[str]]] = []

    def target(name: str) -> Target:
        return targets.setdefault(name, Target(name))

    for f in sorted(files):
        if posixpath.basename(f) != "CMakeLists.txt" and not f.endswith(".cmake"):
            continue
        try:
            text = read(f)
        except OSError:
            continue
        text = re.sub(r"(?m)#.*$", "", text)
        cmake_dir = posixpath.dirname(f)
        variables: dict[str, list[str]] = {}
        pos = 0
        while True:
            m = _CALL.search(text, pos)
            if not m:
                break
            name = m.group(1).lower()
            args, pos = _args(text, m.end() - 1)
            toks = []
            for raw in _tokens(args):
                toks.extend(_expand(raw, variables))
            if not toks:
                continue
            if name == "set" and len(toks) >= 1:
                variables[toks[0]] = toks[1:]
            elif name == "list" and len(toks) >= 2 and toks[0].upper() == "APPEND":
                variables.setdefault(toks[1], []).extend(toks[2:])
            elif "add_library" in name or "add_executable" in name or "add_test" in name:
                is_test = "add_test" in name
                if name == "add_test":
                    # add_test(NAME n COMMAND t ...) | add_test(n t ...)
                    if toks[0].upper() == "NAME" and len(toks) >= 2:
                        n = toks[1]
                        cmd = (
                            toks[toks.index("COMMAND") + 1]
                            if "COMMAND" in toks and toks.index("COMMAND") + 1 < len(toks)
                            else n
                        )
                    else:
                        n, cmd = toks[0], (toks[1] if len(toks) > 1 else toks[0])
                    tests[n] = _bare(cmd)
                    continue
                if name == "add_library" and len(toks) >= 3 and toks[1].upper() == "ALIAS":
                    continue
                tname = toks[0]
                t = target(tname)
                mode = "SOURCES"
                for tok in toks[1:]:
                    up = tok.upper()
                    if up in _KEYWORDS:
                        mode = "DEPS" if up in {"DEPS", "PUBLIC_DEPS", "PRIVATE_DEPS"} else up
                        continue
                    if up in _TYPES or up in {"UMBRELLA", "NO_CTEST", "WIN32", "MACOSX_BUNDLE"}:
                        continue
                    if mode == "DEPS":
                        t.deps.add(_bare(tok))
                    elif mode == "SOURCES" and tok.lower().endswith(_SRC_EXT):
                        t.sources.add(_rel(cmake_dir, tok))
                if is_test:
                    t.is_test = True
                    tests.setdefault(tname, tname)
            elif name == "target_link_libraries" and len(toks) >= 2:
                pending_links.append((toks[0], toks[1:]))

    for tname, deps in pending_links:
        t = target(tname)
        for d in deps:
            if d.upper() not in {"PUBLIC", "PRIVATE", "INTERFACE"}:
                t.deps.add(_bare(d))
    return CMakeGraph(targets=targets, tests=tests)


def _rel(cmake_dir: str, path: str) -> str:
    if path.startswith("//"):
        return posixpath.normpath(path[2:])
    if path.startswith("/"):
        return path
    return posixpath.normpath(posixpath.join(cmake_dir, path))
