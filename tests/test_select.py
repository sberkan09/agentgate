from __future__ import annotations

from agentgate.config import Config, TestMap
from agentgate.select import select_tests

CMAKE = """
add_test(NAME smoke_x COMMAND true)
"""
CMAKE_A = "add_executable(unit_a a_test.cpp)\nadd_test(NAME unit_a COMMAND unit_a)\n"
CMAKE_B = "add_executable(unit_b b_test.cpp)\nadd_test(NAME unit_b COMMAND unit_b)\n"


def cfg(**kw) -> Config:
    base = {"base": "main", "remote": "", "history_window": 0, "roots": ["src", "tests"]}
    return Config(**{**base, **kw})


def ctest_repo(sandbox, branch=True):
    sandbox.commit(
        "base",
        {
            "CMakeLists.txt": "# root\n",
            "src/lib/core.h": "// core\n",
            "src/lib/mid.h": '#include "lib/core.h"\n',
            "tests/smoke/CMakeLists.txt": CMAKE,
            "tests/a/CMakeLists.txt": CMAKE_A,
            "tests/b/CMakeLists.txt": CMAKE_B,
            "tests/a/a_test.cpp": '#include "lib/mid.h"\n',
            "tests/b/b_test.cpp": "int main(){}\n",
        },
    )
    if branch:
        sandbox.branch("feat")


def run(sandbox, c, files):
    sandbox.commit("change", files)
    return select_tests(sandbox.repo, c)


def test_ignore_only_is_none(sandbox):
    ctest_repo(sandbox)
    r = run(sandbox, cfg(runner="ctest"), {"docs/x.txt": "1", "NOTES.md": "1"})
    assert r.mode == "none" and r.tests == []
    assert "docs/x.txt" in r.changed_files


def test_full_on_hit(sandbox):
    ctest_repo(sandbox)
    r = run(
        sandbox,
        cfg(runner="ctest", full_on=["CMakeLists.txt"]),
        {"tests/smoke/CMakeLists.txt": CMAKE + "#\n"},
    )
    assert r.mode == "full" and "tests/smoke/CMakeLists.txt" in (r.full_reason or "")
    assert r.runner_args() == ""


def test_map_and_always_rules(sandbox):
    ctest_repo(sandbox)
    c = cfg(
        runner="ctest",
        always=["^smoke_"],
        maps=[TestMap(paths=["tools/**"], tests=["^unit_b$"])],
    )
    r = run(sandbox, c, {"tools/x/y.py": "1"})
    assert r.mode == "subset"
    assert r.tests == ["smoke_x", "unit_b"]
    why = {x.test: x.why for x in r.reasons}
    assert why["smoke_x"] == "always" and why["unit_b"] == "map:tools/**"
    assert r.total_tests == 3


def test_cpp_transitive_header_selects_test(sandbox):
    ctest_repo(sandbox)
    r = run(sandbox, cfg(runner="ctest"), {"src/lib/core.h": "// changed\n"})
    assert r.tests == ["unit_a"]
    assert r.reasons[0].why == "dep:src/lib/core.h"
    assert r.runner_args() == "^(unit_a)$"


def test_test_file_change_selects_itself(sandbox):
    ctest_repo(sandbox)
    r = run(sandbox, cfg(runner="ctest"), {"tests/b/b_test.cpp": "int main(){return 1;}\n"})
    assert [(x.test, x.why) for x in r.reasons if x.test == "unit_b"] == [("unit_b", "test-file")]


def test_history_cochange_selects_test(sandbox):
    ctest_repo(sandbox, branch=False)
    sandbox.commit("pair1", {"src/other.cpp": "1", "tests/b/b_test.cpp": "1"})
    sandbox.commit("pair2", {"src/other.cpp": "2", "tests/b/b_test.cpp": "2"})
    sandbox.branch("feat")
    r = run(sandbox, cfg(runner="ctest", history_window=50), {"src/other.cpp": "3"})
    assert r.tests == ["unit_b"]
    assert r.reasons[0].why == "history:tests/b/b_test.cpp"


def test_pytest_import_closure_and_test_file(sandbox):
    sandbox.commit(
        "base",
        {
            "src/pkg/__init__.py": "",
            "src/pkg/core.py": "",
            "src/pkg/mid.py": "from pkg import core\n",
            "tests/test_mid.py": "import pkg.mid\n",
            "tests/test_other.py": "import os\n",
        },
    )
    sandbox.branch("feat")
    c = cfg(runner="pytest")
    r = run(sandbox, c, {"src/pkg/core.py": "x = 1\n"})
    assert r.tests == ["tests/test_mid.py"]
    assert r.reasons[0].why == "dep:src/pkg/core.py"
    assert r.total_tests == 2
    assert r.runner_args() == "tests/test_mid.py"
    r = run(sandbox, c, {"tests/test_other.py": "import sys\n"})
    assert ("tests/test_other.py", "test-file") in [(x.test, x.why) for x in r.reasons]


def test_degrades_without_cmake_or_history(sandbox):
    sandbox.branch("feat")
    r = run(sandbox, cfg(runner="ctest", history_window=5, always=["^x"]), {"src/a.cpp": "1"})
    assert r.mode == "subset" and r.full_reason is None
    assert r.total_tests is None
    assert r.tests == ["^x"]  # undiscoverable: identifiers pass through unexpanded
    assert r.reasons[-1].why.startswith("note:")
