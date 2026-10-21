from agentgate.git import find_repo


def test_changed_files_against_base(sandbox):
    sandbox.commit("base", {"src/a.py": "x = 1\n"})
    sandbox.branch("claude/t1")
    sandbox.commit("change", {"src/b.py": "y = 2\n"})
    assert sandbox.repo.changed_files("main") == ["src/b.py"]


def test_branches_by_pattern(sandbox):
    sandbox.branch("claude/t1")
    sandbox.checkout("main")
    sandbox.branch("codex/t2")
    sandbox.as_remote_tracking()
    assert sandbox.repo.branches("claude/*") == ["origin/claude/t1"]
    assert sandbox.repo.branches("codex/*") == ["origin/codex/t2"]


def test_find_repo(sandbox):
    sandbox.commit("src", {"src/a.py": "x = 1\n"})
    assert find_repo(sandbox.root / "src").root == sandbox.root.resolve()
