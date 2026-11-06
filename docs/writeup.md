# Running CI for agents, not people: what 769 agent PRs on one repo taught us

*Draft for a blog post / HN submission. Numbers from `docs/measurement.md`; nothing here is projected.*

## The setup

One developer, one C++ game engine (~1,800 source files, ~260 ctest tests), and several Claude Code
sessions working in parallel on `claude/*` branches. Between 2026-10-21 and 2026-11-06 the repository
took **469 pull requests**, every one of them opened by an agent. The year before that it had taken 673.

CI was a hand-written shell script, `local_ci.sh --task`, that tried to scope the build and the tests to
the change with path rules: "if only docs changed skip GPU tests", "if a CMake file changed run
everything". Each run took 20–25 minutes cold. The script was good; it was also 1,000 lines and only its
author could extend it.

Two things kept going wrong, and they are the two things that go wrong whenever several agents share a
repository:

1. **The full suite ran almost every time.** The path rules said "full" on 87% of PRs, because almost any
   real change touches something the rules could not reason about.
2. **Branches collided.** Agents branch from the base, work for hours, and come back to a base that moved.
   Nobody told them which open branch they were about to collide with, or that their own branch no longer
   merged cleanly.

## What we built

`agentgate` is a 1,000-line, dependency-free Python CLI and a composite GitHub Action. It answers two
questions on every PR and posts the answer as one sticky comment:

**Which tests can observe this change?** From the changed files it walks three graphs, all built from the
repository itself with no build step:

- the `#include` graph (a changed header → the translation units that include it);
- the CMake link graph (a changed `.cpp` → its `add_library` target → every test that links it,
  transitively; project macros with `SOURCES`/`DEPS` lists are understood);
- co-change history (files that moved together with the changed files in the last 200 commits).

A path-to-test map and an "always run" list cover what graphs cannot see, and a `full_on` list
(`cmake/**`, `CMakePresets.json`) says when to give up and run everything. Output: a `ctest -R` regex, or a
pytest path list.

**Which open branches will this conflict with?** `git merge-tree --write-tree` between every pair of open
agent branches, but not between the raw branches: each branch is first previewed on top of the base
(a throwaway `commit-tree`), and the previews are compared with `--merge-base=<base>`. Comparing raw
branches reports the base's own changes as a conflict whenever a branch is behind it, which with several
agents is always. A branch that conflicts with the base itself is listed separately as "rebase first".

## What the numbers say

Offline replay on the last 300 merged PRs (checkout at each merge commit, select, compare with a Python
port of the hand-written rules):

| | hand-written rules | agentgate |
| --- | ---: | ---: |
| full suite | 87% of PRs | 6% |
| nothing to run | 12% | 12% |
| subset | 1% | 82%, mean 32% of the suite, median 33% |

Recall proxy: in all 300 PRs, every test whose own sources changed was selected (397 such tests in 210
PRs). There is no real failure data behind this; it is the check we could run.

Live, 16 days, 57 PRs sampled: subset PRs selected a mean 18% and a median 5% of the suite. Many agent
PRs are small (3–5 files, 1–7 tests of ~260); PRs that touch core headers still pull in 120–178 tests,
which is the include graph telling the truth about a wide header.

## What we got wrong first

- **Raw pairwise merge-tree.** The first version flagged 19 conflicting pairs among 12 branches. After
  previewing on the base: 0 pairs, 5 branches that needed a rebase. Same data, different question.
- **"Open branch" meant "branch that exists".** Merged-but-undeleted branches were filtered early.
  Abandoned branches were not: 6 of the 9 branches in every "rebase first" table for two weeks had no
  open PR. The action now takes the heads of open PRs as the branch set.
- **Include graph only.** Nothing includes a `.cpp`, so a change to `world2d.cpp` selected zero tests until
  the link graph existed. The reason column (`dep:`, `link:`, `history:`) made that visible on the first
  real PR.
- **Runner has no git identity.** `commit-tree` fails on a fresh GitHub runner; the throwaway commit now
  carries its own author.

## What it is not

It is not a replacement for a full run before merging; the full suite still runs in the merge queue.
It has no model and no service; it reads the repository and runs in about a second. It knows C/C++ with
CMake and Python with pytest; other build systems need a path map or an adapter.

## Try it

```yaml
- uses: sberkan09/agentgate@main
  with:
    base: main
    agent-branches: "claude/*,codex/*,copilot/*"
```

MIT. Issues and adapters for other build systems welcome: https://github.com/sberkan09/agentgate
