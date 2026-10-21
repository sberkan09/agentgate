"""Task-scoped test selection: changed files -> the tests that can observe the change.

Contract (implemented in task #4):

    select_tests(repo, cfg, head="HEAD", include_untracked=False) -> SelectionReport

Decision order:
1. changed = repo.changed_files(cfg.base_ref, head). Drop files matching cfg.ignore. Empty -> mode "none".
2. Any changed file matching cfg.full_on -> mode "full" (full_reason names the file).
3. Otherwise a subset, the union of:
   - cfg.always (reason "always");
   - cfg.maps whose path glob matches a changed file (reason "map:<glob>");
   - tests whose own source file changed (reason "test-file");
   - static dependency closure: a changed header/module -> the translation units / modules that include or
     import it (transitively) -> the tests built from or importing those (reason "dep:<file>").
     Adapters per language in ``deps/``: cpp (#include graph by path and basename), python (import graph).
   - co-change history: files that changed together with the changed files in the last
     cfg.history_window commits, when those files are tests (reason "history:<file>").
4. Test identity depends on cfg.runner:
   - ctest: test names (from ``ctest --show-only=json-v1`` when a build dir is given, else from
     add_test()/mce_add_test() patterns in CMakeLists via the discovery adapter); runner_args() is a -R regex.
   - pytest: test file paths; runner_args() is the path list.
   - command: whatever identifiers the maps name.
5. total_tests when discoverable, else None. Never raise on an unknown language or missing build dir:
   degrade to the maps + always + test-file rules and say so in a reason.
"""

from __future__ import annotations

import posixpath
import re
from functools import lru_cache

from .config import Config
from .deps import closure, cmake, cpp, discover, history
from .deps import python as pydeps
from .git import Repo
from .report import SelectionReason, SelectionReport

NOTE_TEST = "(agentgate)"


@lru_cache(maxsize=512)
def _glob_re(glob: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out))


def match(path: str, glob: str) -> bool:
    """Glob match: ``**`` crosses directories, ``*``/``?`` do not; a glob without ``/`` matches any depth."""
    path = path.removeprefix("./")
    if "/" not in glob:
        path = posixpath.basename(path)
    return _glob_re(glob.removeprefix("./")).fullmatch(path) is not None


def _under_roots(path: str, roots: list[str]) -> bool:
    for r in roots:
        r = r.strip("/").removeprefix("./")
        if r in ("", "."):
            return True
        if path == r or path.startswith(r + "/"):
            return True
    return False


def _expand(pattern: str, known: list[str], runner: str) -> list[str]:
    """A map/always entry -> test identifiers (regex over discovered names, else the entry itself)."""
    if known:
        try:
            rx = re.compile(pattern)
            hits = [t for t in known if t == pattern or rx.search(t)]
        except re.error:
            hits = [t for t in known if t == pattern]
        if hits or runner == "ctest":
            return hits
    return [pattern]


def select_tests(
    repo: Repo, cfg: Config, head: str = "HEAD", include_untracked: bool = False
) -> SelectionReport:
    raw = repo.changed_files(cfg.base_ref, head, include_untracked)
    report = SelectionReport(
        base=cfg.base_ref,
        head=head,
        changed_files=raw,
        mode="none",
        tests=[],
        total_tests=None,
        runner=cfg.runner,
    )
    changed = [f for f in raw if not any(match(f, g) for g in cfg.ignore)]
    if not changed:
        return report

    for f in changed:
        if any(match(f, g) for g in cfg.full_on):
            report.mode = "full"
            report.full_reason = f"`{f}` matches full_on"
            return report
    report.mode = "subset"

    notes: list[str] = []
    all_files = repo.ls_files()
    if include_untracked:
        all_files += repo.out("ls-files", "--others", "--exclude-standard").splitlines()
    all_files = sorted({f for f in all_files if f})
    scoped = [f for f in all_files if _under_roots(f, cfg.roots)]

    def read(path: str) -> str:
        return repo.read_file(path)

    # --- discovery ---
    names: list[str] = []
    ct_index: discover.CtestIndex | None = None
    py_tests: list[str] = []
    graph: cmake.CMakeGraph | None = None
    if cfg.runner == "ctest":
        defs = discover.discover_ctest(read, all_files)
        graph = cmake.parse_graph(read, all_files)
        names = sorted({t.name for t in defs} | set(graph.tests))
        ct_index = discover.CtestIndex(defs)
        if not names:
            notes.append("no CMake add_test() found; only always/map rules apply")
    elif cfg.runner == "pytest":
        py_tests = discover.discover_pytest(scoped)
        names = py_tests
        if not py_tests:
            notes.append("no pytest files found; only always/map rules apply")
    report.total_tests = len(names) or None

    reasons: dict[str, str] = {}

    def add(test: str, why: str) -> None:
        reasons.setdefault(test, why)

    # --- rules, in contract order ---
    for pat in cfg.always:
        for t in _expand(pat, names, cfg.runner):
            add(t, "always")
    for m in cfg.maps:
        for f in changed:
            glob = next((g for g in m.paths if match(f, g)), None)
            if glob is not None:
                for pat in m.tests:
                    for t in _expand(pat, names, cfg.runner):
                        add(t, f"map:{glob}")

    changed_set = set(changed)
    if ct_index is not None:
        for f in changed:
            for t in ct_index.lookup(f):
                add(t, "test-file")
        if "cpp" not in cfg.languages:
            notes.append("cpp dependency analysis disabled (deps.languages)")
        else:
            srcs = [f for f in scoped if cpp.is_cpp(f)]
            changed_cpp = [f for f in changed if cpp.is_cpp(f)]
            reach: dict[str, str] = {}
            if srcs:
                reach = closure(cpp.build_reverse(read, srcs), changed_cpp)
                for f, origin in sorted(reach.items()):
                    if f not in changed_set:
                        for t in ct_index.lookup(f):
                            add(t, f"dep:{origin}")
            else:
                notes.append("no C/C++ files under deps.roots")
            # Link graph: a changed or reached source belongs to a target; every test that links that
            # target (transitively) observes the change even though nothing #includes a .cpp.
            if graph is not None and graph.targets:
                origin_of = {f: f for f in changed_cpp}
                origin_of.update({f: o for f, o in reach.items() if f not in origin_of})
                for test, f in graph.tests_for_files(list(origin_of)).items():
                    add(test, f"link:{origin_of[f]}")
    elif cfg.runner == "pytest":
        for f in changed:
            if f in py_tests:
                add(f, "test-file")
        if "python" not in cfg.languages:
            notes.append("python dependency analysis disabled (deps.languages)")
        else:
            pys = [f for f in scoped if pydeps.is_python(f)]
            reach = closure(pydeps.build_reverse(read, pys), [f for f in changed if pydeps.is_python(f)])
            for f, origin in sorted(reach.items()):
                if f in py_tests and f not in changed_set:
                    add(f, f"dep:{origin}")
            for f in changed:
                if posixpath.basename(f) == "conftest.py":
                    d = posixpath.dirname(f)
                    for t in py_tests:
                        if not d or t.startswith(d + "/"):
                            add(t, f"dep:{f}")

    if cfg.history_window > 0 and cfg.runner in ("ctest", "pytest"):
        co = history.cochange(repo, changed, cfg.history_window)
        if co is None:
            notes.append("git history unavailable (shallow clone?); co-change skipped")
        else:
            for other in sorted(co):
                if ct_index is not None:
                    hit = ct_index.lookup(other)
                else:
                    hit = [other] if other in py_tests else []
                for t in hit:
                    add(t, f"history:{other}")

    report.tests = sorted(reasons)
    report.reasons = [SelectionReason(t, reasons[t]) for t in report.tests]
    if notes:
        report.reasons.append(SelectionReason(NOTE_TEST, "note: " + "; ".join(notes)))
    return report
