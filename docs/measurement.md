# agentgate measurement: mesh_control_engine

Replay of `origin/dev_claude` first-parent merges (last 300 PRs), config `mesh_control_engine.agentgate.toml`.

## Method and limits
- Per PR: base = first parent, head = merge commit; working tree checked out at the merge commit.
- `select_tests` runs with `remote=""`, `base=<first parent sha>`, ctest names from CMake parsing (no build).
- Hand rule = Python port of `gpu_irrelevant`/`sim_only`/`test_scope`/`touches_cmake` in `scripts/ci/local_ci.sh`;
  it decides on test labels (gpu/sdk/slow), agentgate on test names, so only the verdicts are compared.
- No real test failure data: recall proxy only checks that tests whose own target sources changed are selected.
- Select errors: 0. Wall time 108s, mean 0.333s per select.

## agentgate mode
| mode | PRs | share |
| --- | ---: | ---: |
| full | 18 | 6.0% |
| subset | 246 | 82.0% |
| none | 36 | 12.0% |

Subset PRs: 246; selected fraction mean 31.9%, median 33.0%.
PRs with <= 50% of tests selected (subset or none): 227/300 (75.7%).

## Hand rule (local_ci.sh test_scope)
| scope | PRs | share |
| --- | ---: | ---: |
| full | 261 | 87.0% |
| smoke | 3 | 1.0% |
| nongpu | 36 | 12.0% |

## agentgate mode x hand scope (PRs)
| agentgate \ hand | full | smoke | nongpu |
| --- | ---: | ---: | ---: |
| full | 18 | 0 | 0 |
| subset | 243 | 3 | 0 |
| none | 0 | 0 | 36 |

## Largest subset selections
| PR | selected/total | changed | top files |
| ---: | ---: | ---: | --- |
| #542 | 173/214 | 11 | `changelog.d/WORKFLOW-7-defaults-load.md`, `docs/milestones/M-WORKFLOW.md`, `docs/user-guide/12-ui-and-console.md` (+8) |
| #527 | 167/205 | 8 | `changelog.d/WORKFLOW-7-convar-defaults.md`, `docs/milestones/M-WORKFLOW.md`, `docs/user-guide/12-ui-and-console.md` (+5) |
| #502 | 158/202 | 6 | `changelog.d/OPENWORLD-2-worldpoint-seam.md`, `docs/engine/refl.md`, `docs/milestones/M-OPENWORLD.md` (+3) |
| #516 | 152/205 | 44 | `changelog.d/OPENWORLD-2-floating-origin.md`, `docs/engine/capabilities.md`, `docs/engine/ecs.md` (+41) |
| #591 | 150/225 | 25 | `changelog.d/GH-406-items-catalog.md`, `docs/engine/capabilities.md`, `docs/milestones/M-FUZZ.md` (+22) |
| #480 | 144/201 | 24 | `changelog.d/SBA-199-static-merge.md`, `docs/engine/capabilities.md`, `docs/user-guide/08-3d.md` (+21) |
| #500 | 143/204 | 37 | `changelog.d/GH-500-road-network.md`, `docs/adr/0046-road-network.md`, `docs/adr/README.md` (+34) |
| #541 | 139/209 | 20 | `changelog.d/WORKFLOW-7-defaults-chunk.md`, `docs/engine/capabilities.md`, `docs/milestones/M-WORKFLOW.md` (+17) |
| #300 | 139/151 | 24 | `docs/ROADMAP.md`, `docs/engine/capabilities.md`, `docs/engine/kit.md` (+21) |
| #333 | 137/167 | 18 | `CHANGELOG.md`, `docs/milestones/M-SCRIPT.md`, `docs/user-guide/27-scripting.md` (+15) |

## Recall proxy
Own-source tests selected in 300/300 PRs; failing: 0.
