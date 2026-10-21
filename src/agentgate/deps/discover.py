"""Test discovery: ctest tests from CMakeLists, pytest tests from file layout."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from . import Reader

_ADD_TEST = re.compile(r"\b\w*add_test\w*\(\s*(?:NAME\s+)?([A-Za-z0-9_.-]+)", re.IGNORECASE)
_ADD_EXE = re.compile(r"\badd_executable\s*\(\s*([A-Za-z0-9_.-]+)", re.IGNORECASE)
_SRC_EXT = (".cpp", ".cc", ".cxx", ".c")


@dataclass
class CtestTest:
    name: str
    dir: str  # directory of the defining CMakeLists.txt ("" = repo root)
    sources: list[str] = field(default_factory=list)  # repo-relative


def _args(text: str, start: int) -> str:
    """Text from ``start`` (just after an opening paren's name) to the matching close paren."""
    depth, i = 0, text.index("(", start)
    begin = i + 1
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[begin:i]
        i += 1
    return text[begin:]


def _sources(cmake_dir: str, args: str) -> list[str]:
    out = []
    for tok in re.split(r"\s+", args):
        tok = tok.strip("\"'")
        if tok.endswith(_SRC_EXT):
            tok = re.sub(r"^\$\{[^}]*\}/?", "", tok)
            if "$" not in tok and tok:
                out.append(posixpath.normpath(posixpath.join(cmake_dir, tok)))
    return out


def discover_ctest(read: Reader, files: list[str]) -> list[CtestTest]:
    tests: dict[str, CtestTest] = {}
    for f in files:
        if posixpath.basename(f) != "CMakeLists.txt":
            continue
        try:
            text = read(f)
        except OSError:
            continue
        text = re.sub(r"(?m)#.*$", "", text)
        d = posixpath.dirname(f)
        exes = {m.group(1): _sources(d, _args(text, m.start())) for m in _ADD_EXE.finditer(text)}
        for m in _ADD_TEST.finditer(text):
            name = m.group(1)
            if name.upper() == "NAME":
                continue
            args = _args(text, m.start())
            srcs = _sources(d, args)
            for tok in re.split(r"[\s()]+", args):
                srcs += exes.get(tok, [])
            srcs += exes.get(name, [])
            t = tests.setdefault(name, CtestTest(name, d))
            t.sources = sorted(set(t.sources) | set(srcs))
    return sorted(tests.values(), key=lambda t: t.name)


class CtestIndex:
    """Lookup: which tests does a file belong to (as a source, or by living in the test's directory)?"""

    def __init__(self, tests: list[CtestTest]):
        self.by_source: dict[str, list[str]] = {}
        self.by_dir: dict[str, list[str]] = {}
        for t in tests:
            for s in t.sources:
                self.by_source.setdefault(s, []).append(t.name)
            if t.dir:  # a root-level CMakeLists would make every file "belong" to its tests
                self.by_dir.setdefault(t.dir, []).append(t.name)

    def lookup(self, path: str) -> list[str]:
        found = list(self.by_source.get(path, ()))
        d = posixpath.dirname(path)
        while d:
            found += self.by_dir.get(d, ())
            d = posixpath.dirname(d)
        return list(dict.fromkeys(found))


def is_pytest_file(path: str) -> bool:
    base = posixpath.basename(path)
    return path.endswith(".py") and ((base.startswith("test_")) or base.endswith("_test.py"))


def discover_pytest(files: list[str]) -> list[str]:
    return sorted(f for f in files if is_pytest_file(f))
