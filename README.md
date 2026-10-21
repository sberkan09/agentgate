# agentgate

CI for pull requests opened by AI coding agents. Two checks, one GitHub Action, no server:

1. **Conflict forecast.** Before anything merges, `git merge-tree` is run between every pair of open agent
   branches (`claude/*`, `codex/*`, `copilot/*`, …). Pairs that would conflict are reported on the PR,
   with a suggested merge order, while both branches are still cheap to rebase.
2. **Task-scoped test selection.** From the files a PR changes, agentgate selects the tests that can
   observe the change (a static dependency graph, path-to-test maps, co-change history) and prints the
   argument your runner needs (`ctest -R …`, `pytest paths…`). The full suite runs only in the merge queue.

Why: with several agents working in parallel, CI minutes and merge conflicts grow with the number of
agents, not the number of engineers. Studies of agent PRs put the conflicting-pair rate at roughly 40% of
repositories; a single agent session can burn a month of Actions minutes in an afternoon.

## Install

```
pip install agentgate          # Python 3.11+, git 2.38+ (merge-tree --write-tree), no other dependencies
```

## Use

```
agentgate conflicts --base main                 # all pairs among open agent branches
agentgate conflicts --base main --head claude/foo --fail-on-conflict
agentgate select --base main --format args      # e.g. "^(physics2d_a|physics2d_b)$" for ctest -R
agentgate select --base main --format json --output build/agentgate/select.json
```

Configure with `agentgate.toml` in the repo root (see `src/agentgate/config.py` for every key):

```toml
[agentgate]
base = "main"
agent_branches = ["claude/*", "codex/*"]

[tests]
runner = "ctest"
always = ["^smoke_"]
full_on = ["CMakeLists.txt", "cmake/**"]

[[tests.map]]
paths = ["src/engine/physics2d/**", "tests/physics2d/**"]
tests = ["^physics2d_"]
```

## GitHub Action

```yaml
- uses: sberkan09/agentgate@v0
  with:
    base: main
    fail-on-conflict: false
```

The action posts both reports to the job summary and, on pull requests, as a sticky PR comment, and exposes
`tests-args` for the following step.

## Status

0.1, measured on one repository (a C++ game engine with ~670 agent PRs). Numbers in `docs/measurement.md`.

## License

MIT.
