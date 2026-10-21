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

from .config import Config
from .git import Repo
from .report import SelectionReport


def select_tests(
    repo: Repo, cfg: Config, head: str = "HEAD", include_untracked: bool = False
) -> SelectionReport:
    raise NotImplementedError("task #4")
