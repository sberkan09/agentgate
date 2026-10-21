# agentgate measurement: mesh_control_engine

Replay of `origin/dev_claude` first-parent merges (last 300 PRs), config `mesh_control_engine.agentgate.toml`.

## Method and limits
- Per PR: base = first parent, head = merge commit; working tree checked out at the merge commit.
- `select_tests` runs with `remote=""`, `base=<first parent sha>`, ctest names from CMake parsing (no build).
- Hand rule = Python port of `gpu_irrelevant`/`sim_only`/`test_scope`/`touches_cmake` in `scripts/ci/local_ci.sh`;
  it decides on test labels (gpu/sdk/slow), agentgate on test names, so only the verdicts are compared.
- No real test failure data: recall proxy only checks that tests whose own target sources changed are selected.
- Select errors: 0. Wall time 113s, mean 0.348s per select.

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
| #542 | 173/214 | 11 | `projects/Undertow/assets/defaults.mcdefaults`, `src/engine/asset/cook/src/cook.cpp`, `src/engine/asset/src/asset_system.cpp` (+5) |
| #527 | 167/205 | 8 | `src/engine/core/include/mce/convar.h`, `src/engine/core/src/convar.cpp`, `src/player/src/player.cpp` (+1) |
| #502 | 158/202 | 6 | `src/editor/mcp/src/values.cpp`, `src/engine/refl/include/mce/refl/macros.h`, `src/engine/refl/include/mce/refl/type.h` |
| #516 | 152/205 | 44 | `scripts/ci/sample_coverage.allow`, `src/engine/ecs/CMakeLists.txt`, `src/engine/ecs/include/mce/ecs/origin.h` (+31) |
| #591 | 150/225 | 25 | `src/editor/core/src/project.cpp`, `src/editor/mcp/src/asset_tools.cpp`, `src/engine/asset/CMakeLists.txt` (+17) |
| #480 | 144/201 | 24 | `scripts/ci/sample_coverage.allow`, `src/editor/core/src/engine_components.cpp`, `src/editor/core/src/perf_file.cpp` (+17) |
| #500 | 143/204 | 37 | `scripts/ci/sample_coverage.allow`, `src/editor/core/src/engine_components.cpp`, `src/editor/core/src/project.cpp` (+25) |
| #541 | 139/209 | 20 | `src/editor/core/src/project.cpp`, `src/editor/mcp/src/asset_tools.cpp`, `src/engine/asset/cook/CMakeLists.txt` (+12) |
| #300 | 139/151 | 24 | `src/editor/core/src/engine_components.cpp`, `src/editor/mcp/app/engine_components.cpp`, `src/engine/core/include/mce/fixed_string.h` (+14) |
| #333 | 137/167 | 18 | `samples/script_headless/main.cpp`, `src/engine/ecs/include/mce/ecs/world.h`, `src/engine/kit/include/mce/kit/bodies3d.h` (+12) |

## Recall proxy
Own-source tests selected in 300/300 PRs; failing: 0.
