"""agentgate.toml: the repo's description of its agents, tests and modules.

Minimal example::

    [agentgate]
    base = "main"
    agent_branches = ["claude/*", "codex/*", "copilot/*"]

    [tests]
    runner = "ctest"            # ctest | pytest | command
    always = ["^smoke_"]        # test-name regexes that run on every change
    full_on = ["CMakeLists.txt", "cmake/**", "pyproject.toml"]   # globs: any match -> run everything

    [[tests.map]]               # path glob -> tests (name regexes or test paths)
    paths = ["src/engine/physics2d/**", "tests/physics2d/**"]
    tests = ["^physics2d_"]

    [deps]
    languages = ["cpp", "python"]   # static dependency graphs to build
    roots = ["src", "tests", "samples"]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "agentgate.toml"


@dataclass
class TestMap:
    paths: list[str]
    tests: list[str]


@dataclass
class Config:
    base: str = "main"
    remote: str = "origin"
    agent_branches: list[str] = field(
        default_factory=lambda: ["claude/*", "codex/*", "copilot/*", "cursor/*"]
    )
    runner: str = "command"
    always: list[str] = field(default_factory=list)
    full_on: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=lambda: ["**/*.md", "docs/**", ".github/**"])
    maps: list[TestMap] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["cpp", "python"])
    roots: list[str] = field(default_factory=lambda: ["."])
    history_window: int = 200  # commits of co-change history to consult

    @property
    def base_ref(self) -> str:
        return f"{self.remote}/{self.base}" if self.remote else self.base


def load(path: Path | None) -> Config:
    """Loads ``agentgate.toml`` from ``path`` (a file or a directory); missing file -> defaults."""
    if path is None:
        return Config()
    file = path / CONFIG_NAME if path.is_dir() else path
    if not file.exists():
        return Config()
    data = tomllib.loads(file.read_text())
    ag = data.get("agentgate", {})
    tests = data.get("tests", {})
    deps = data.get("deps", {})
    cfg = Config()
    cfg.base = ag.get("base", cfg.base)
    cfg.remote = ag.get("remote", cfg.remote)
    cfg.agent_branches = ag.get("agent_branches", cfg.agent_branches)
    cfg.runner = tests.get("runner", cfg.runner)
    cfg.always = tests.get("always", cfg.always)
    cfg.full_on = tests.get("full_on", cfg.full_on)
    cfg.ignore = tests.get("ignore", cfg.ignore)
    cfg.maps = [TestMap(paths=m["paths"], tests=m["tests"]) for m in tests.get("map", [])]
    cfg.languages = deps.get("languages", cfg.languages)
    cfg.roots = deps.get("roots", cfg.roots)
    cfg.history_window = int(deps.get("history_window", cfg.history_window))
    return cfg
