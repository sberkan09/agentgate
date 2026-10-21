from __future__ import annotations

from agentgate.config import Config
from agentgate.conflicts import forecast

BASE = "line1\nline2\nline3\n"


def make(sandbox, name: str, files: dict[str, str]) -> None:
    sandbox.branch(name)
    sandbox.commit(name, files)
    sandbox.checkout("main")


def cfg() -> Config:
    c = Config()
    c.remote = "origin"
    c.base = "main"
    return c


def setup(sandbox, specs: dict[str, dict[str, str]]):
    sandbox.commit("shared", {"shared.txt": BASE})
    for name, files in specs.items():
        make(sandbox, name, files)
    sandbox.as_remote_tracking()
    return sandbox.repo


def test_disjoint_files_no_pairs(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}, "claude/b": {"b.txt": "b\n"}})
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert r.pairs == [] and not r.conflicting and r.errors == []
    assert sorted(r.branches) == ["origin/claude/a", "origin/claude/b"]


def test_same_line_conflict(sandbox):
    repo = setup(
        sandbox,
        {
            "claude/a": {"shared.txt": "line1\nA\nline3\n"},
            "claude/b": {"shared.txt": "line1\nB\nline3\n"},
        },
    )
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert len(r.pairs) == 1
    assert r.pairs[0].files == ["shared.txt"]
    assert {r.pairs[0].a, r.pairs[0].b} == {"origin/claude/a", "origin/claude/b"}


def test_head_filter_only_pairs_with_head(sandbox):
    repo = setup(
        sandbox,
        {
            "claude/a": {"shared.txt": "line1\nA\nline3\n"},
            "claude/b": {"shared.txt": "line1\nB\nline3\n"},
            "claude/c": {"shared.txt": "line1\nC\nline3\n"},
        },
    )
    r = forecast(repo, cfg(), head="claude/a", patterns=["claude/*"])
    assert r.head == "origin/claude/a"
    assert len(r.pairs) == 2
    assert all(p.a == "origin/claude/a" for p in r.pairs)


def test_head_not_matching_pattern_is_added(sandbox):
    repo = setup(
        sandbox,
        {"claude/a": {"shared.txt": "line1\nA\nline3\n"}, "feature/x": {"shared.txt": "line1\nX\nline3\n"}},
    )
    r = forecast(repo, cfg(), head="feature/x", patterns=["claude/*"])
    assert "feature/x" in r.branches  # resolved as given (local ref exists)
    assert len(r.pairs) == 1


def test_merge_order_clean_first(sandbox):
    repo = setup(
        sandbox,
        {
            "claude/a": {"shared.txt": "line1\nA\nline3\n"},
            "claude/b": {"shared.txt": "line1\nB\nline3\n"},
            "claude/clean": {"c.txt": "c\n"},
        },
    )
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert r.merge_order[0] == "origin/claude/clean"
    assert sorted(r.merge_order) == sorted(r.branches)


def test_no_matching_pattern_empty_report(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}})
    r = forecast(repo, cfg(), patterns=["nomatch/*"])
    assert r.branches == [] and r.pairs == [] and r.merge_order == [] and r.errors == []


def test_base_branch_excluded(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}})
    r = forecast(repo, cfg(), patterns=["*", "claude/*"])
    assert "origin/main" not in r.branches
    assert r.branches == ["origin/claude/a"]


def test_max_branches_truncates_with_error(sandbox):
    repo = setup(sandbox, {f"claude/{i}": {f"{i}.txt": "x\n"} for i in range(4)})
    r = forecast(repo, cfg(), patterns=["claude/*"], max_branches=2)
    assert len(r.branches) == 2
    assert any("max_branches" in e for e in r.errors)


def test_unrelated_histories_recorded_as_error(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}})
    from conftest import git

    git(sandbox.root, "checkout", "-q", "--orphan", "claude/solo")
    sandbox.commit("solo", {"solo.txt": "s\n"})
    sandbox.as_remote_tracking()
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert any("no merge base" in e for e in r.errors)


def test_unresolvable_head_is_error(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}})
    r = forecast(repo, cfg(), head="claude/ghost", patterns=["claude/*"])
    assert r.pairs == [] and r.errors


def test_merged_branches_are_not_open(sandbox):
    repo = setup(sandbox, {"claude/a": {"a.txt": "a\n"}, "claude/b": {"b.txt": "b\n"}})
    sandbox.checkout("main")
    sandbox.repo.run("merge", "-q", "--no-ff", "-m", "merge a", "claude/a")
    sandbox.as_remote_tracking()
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert r.branches == ["origin/claude/b"]


def test_behind_base_is_a_base_conflict_not_a_pair(sandbox):
    # a and b branch off, then main edits shared.txt; a edits the same line, b edits another file.
    repo = setup(
        sandbox,
        {"claude/a": {"shared.txt": "line1\nA\nline3\n"}, "claude/b": {"b.txt": "b\n"}},
    )
    sandbox.checkout("main")
    sandbox.commit("main moves", {"shared.txt": "line1\nMAIN\nline3\n"})
    sandbox.as_remote_tracking()
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert [p.a for p in r.base_conflicts] == ["origin/claude/a"]
    assert r.base_conflicts[0].files == ["shared.txt"]
    assert r.pairs == []
    assert r.conflicting


def test_pairs_are_previewed_on_top_of_base(sandbox):
    # Both branches are behind main; main's change must not be reported as their mutual conflict.
    repo = setup(
        sandbox,
        {"claude/a": {"a.txt": "a\n"}, "claude/b": {"b.txt": "b\n"}},
    )
    sandbox.checkout("main")
    sandbox.commit("main moves", {"shared.txt": "line1\nMAIN\nline3\n"})
    sandbox.as_remote_tracking()
    r = forecast(repo, cfg(), patterns=["claude/*"])
    assert r.base_conflicts == [] and r.pairs == []
