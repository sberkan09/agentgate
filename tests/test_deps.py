from __future__ import annotations

from agentgate.deps import closure, cpp, discover, history
from agentgate.deps import python as pydeps
from agentgate.select import match


def test_match_globs():
    assert match("src/a/b.c", "src/**")
    assert match("src/b.c", "src/**")
    assert not match("other/b.c", "src/**")
    assert match("CMakeLists.txt", "CMakeLists.txt")
    assert match("a/b/CMakeLists.txt", "CMakeLists.txt")
    assert match("README.md", "**/*.md")
    assert match("a/b/README.md", "**/*.md")
    assert match("cmake/x/y.cmake", "cmake/**")
    assert match("a/x.c", "a/?.c")
    assert not match("a/b/x.c", "a/*.c")


def test_cpp_include_graph_transitive():
    files = {
        "src/core/a.h": "",
        "src/core/b.h": '#include "a.h"\n',
        "src/core/c.cpp": "#include <core/b.h>\n#include <vector>\n",
        "tests/t.cpp": '#  include "core/c.h"\n',
    }
    rev = cpp.build_reverse(files.__getitem__, sorted(files))
    assert rev["src/core/a.h"] == {"src/core/b.h"}
    reach = closure(rev, ["src/core/a.h"])
    assert set(reach) == {"src/core/a.h", "src/core/b.h", "src/core/c.cpp"}
    assert reach["src/core/c.cpp"] == "src/core/a.h"


def test_python_import_graph():
    files = {
        "pkg/__init__.py": "",
        "pkg/base.py": "",
        "pkg/mid.py": "from pkg import base\n",
        "pkg/rel.py": "from .mid import x\n",
        "tests/test_a.py": "import pkg.rel\n",
        "tests/test_b.py": "import os\n",
    }
    rev = pydeps.build_reverse(files.__getitem__, sorted(files))
    reach = closure(rev, ["pkg/base.py"])
    assert {"pkg/mid.py", "pkg/rel.py", "tests/test_a.py"} <= set(reach)
    assert "tests/test_b.py" not in reach


def test_discover_ctest_macro_and_sources():
    cmake = """
add_executable(unit_x x.cpp helper.cpp)
add_test(NAME unit_x COMMAND unit_x)
mce_add_test(fancy fancy_test.cpp)
macro(mce_add_test name)
endmacro()
add_test(NAME ${t} COMMAND foo)
"""
    tests = discover.discover_ctest({"tests/CMakeLists.txt": cmake}.__getitem__, ["tests/CMakeLists.txt"])
    by = {t.name: t for t in tests}
    assert set(by) == {"unit_x", "fancy"}
    assert by["unit_x"].sources == ["tests/helper.cpp", "tests/x.cpp"]
    assert by["fancy"].sources == ["tests/fancy_test.cpp"]
    idx = discover.CtestIndex(tests)
    assert idx.by_source["tests/x.cpp"] == ["unit_x"]
    assert set(idx.lookup("tests/other.txt")) == {"unit_x", "fancy"}


def test_discover_pytest():
    got = discover.discover_pytest(["a/test_x.py", "a/y_test.py", "a/conftest.py", "a/test_z.txt"])
    assert got == ["a/test_x.py", "a/y_test.py"]


def test_history_cochange(sandbox):
    for i in range(2):
        sandbox.commit(f"c{i}", {"src/a.c": str(i), "tests/t.c": str(i), f"x{i}": "1"})
    sandbox.commit("solo", {"src/a.c": "9", "other.c": "1"})
    assert history.cochange(sandbox.repo, ["src/a.c"], 50) == {"tests/t.c": "src/a.c"}
    assert history.cochange(sandbox.repo, ["src/a.c"], 1) == {}


def test_cmake_link_graph_maps_source_to_linking_tests():
    from agentgate.deps.cmake import parse_graph

    files = {
        "src/lib/CMakeLists.txt": (
            "set(_srcs src/a.cpp src/b.cpp)\nmy_add_library(mylib SOURCES ${_srcs} PUBLIC_DEPS ns::core)\n"
        ),
        "src/core/CMakeLists.txt": "add_library(core STATIC core.cpp)\n",
        "tests/CMakeLists.txt": (
            "my_add_test(test_lib SOURCES test_lib.cpp DEPS ns::mylib)\n"
            "add_executable(other other.cpp)\n"
            "target_link_libraries(other PRIVATE core)\n"
            "add_test(NAME other_test COMMAND other)\n"
            "add_test(NAME unrelated COMMAND ${PROJECT_SOURCE_DIR}/tools/x.py)\n"
        ),
    }
    g = parse_graph(lambda p: files[p], list(files))
    assert g.targets["mylib"].sources == {"src/lib/src/a.cpp", "src/lib/src/b.cpp"}
    assert g.targets["mylib"].deps == {"core"}
    assert g.tests["other_test"] == "other"
    assert g.tests_for_files(["src/lib/src/a.cpp"]) == {"test_lib": "src/lib/src/a.cpp"}
    hit = g.tests_for_files(["src/core/core.cpp"])
    assert set(hit) == {"test_lib", "other_test"}
