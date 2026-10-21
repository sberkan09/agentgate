"""Replay agentgate test selection over the last N merged PRs of a repository and summarise it.

Stdlib only. Method limits are written into the Markdown output.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentgate import config as config_mod
from agentgate.deps import cmake
from agentgate.git import Repo
from agentgate.select import select_tests

PR_RE = re.compile(r"Merge pull request #(\d+)")
CMAKE_RE = re.compile(r"(^|/)CMakeLists\.txt$|^cmake/|^CMakePresets\.json$")
DOC_PREFIXES = ("docs/", "claude_communication/", "changelog.d/", ".claude/")
DOC_FILES = (".clang-format", ".clang-tidy", ".gitignore", ".mcp.json")
NET_PREFIXES = (
    "src/engine/net/", "src/engine/monetize/", "src/engine/liveops/", "src/engine/loc/",
    "tests/net/", "tests/monetize/", "tests/liveops/", "tests/loc/",
)  # fmt: skip
SIM_PREFIXES = (
    "src/engine/core/", "src/engine/ecs/", "src/engine/refl/", "src/engine/scene/",
    "src/engine/physics2d/", "src/engine/physics3d/", "src/engine/script/", "src/engine/audio/",
    "src/engine/input/", "tests/core/", "tests/ecs/", "tests/refl/", "tests/scene/",
    "tests/physics2d/", "tests/physics3d/", "tests/script/", "tests/audio/", "tests/input/",
)  # fmt: skip


def gpu_irrelevant(f: str) -> bool:
    if f.startswith(DOC_PREFIXES) or f.endswith(".md") or f in DOC_FILES:
        return True
    if f.startswith("scripts/ci/"):
        return False
    if f.startswith("scripts/"):
        return True
    return f.startswith(NET_PREFIXES) or (f.startswith("samples/net_") and "/" in f[len("samples/") :])


def sim_only(f: str) -> bool:
    if f.startswith(SIM_PREFIXES):
        return True
    if f.startswith("samples/") and f.split("/")[1].endswith("_headless") and f.count("/") >= 2:
        return True
    return gpu_irrelevant(f)


def hand_scope(files: list[str]) -> str:
    if any(CMAKE_RE.search(f) for f in files):
        return "full"
    scope = "nongpu"
    for f in files:
        if gpu_irrelevant(f):
            continue
        if sim_only(f):
            scope = "smoke"
        else:
            return "full"
    return scope


def reason_counts(reasons: list) -> dict[str, int]:
    c: Counter[str] = Counter()
    for r in reasons:
        if r.test == "(agentgate)":
            continue
        c[r.why.split(":", 1)[0]] += 1
    return dict(c)


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="origin/dev_claude")
    ap.add_argument("--config", required=True)
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--out", default="docs/measurement.json")
    ap.add_argument("--md", default="docs/measurement.md")
    a = ap.parse_args()

    main_repo = Repo(Path(a.repo).resolve())
    log = main_repo.out(
        "log", "--first-parent", "--merges", "--format=%H%x09%P%x09%s", "-n", str(a.n), a.base
    )
    merges = []
    for line in log.splitlines():
        sha, parents, subject = line.split("\t", 2)
        m = PR_RE.search(subject)
        merges.append((sha, parents.split()[0], int(m.group(1)) if m else None, subject))

    tmp = tempfile.mkdtemp(prefix="agentgate-measure-")
    wt = Path(tmp) / "wt"
    main_repo.run("worktree", "add", "--detach", str(wt), merges[0][0])
    wrepo = Repo(wt)
    results = []
    t_all = time.monotonic()
    try:
        for i, (sha, first, num, subject) in enumerate(merges):
            wrepo.run("checkout", "-q", "--detach", sha)
            cfg = config_mod.load(Path(a.config))
            cfg.remote = ""
            cfg.base = first
            rec: dict = {"pr": num, "sha": sha, "base_sha": first, "subject": subject}
            t0 = time.monotonic()
            try:
                rep = select_tests(wrepo, cfg, head=sha)
                rec.update(
                    n_changed=len(rep.changed_files),
                    changed_files=rep.changed_files,
                    mode=rep.mode,
                    n_selected=len(rep.tests),
                    total_tests=rep.total_tests,
                    reasons=reason_counts(rep.reasons),
                    full_reason=rep.full_reason,
                    hand_scope=hand_scope(rep.changed_files),
                )
                # recall proxy: tests whose own target sources changed must be selected
                graph = cmake.parse_graph(wrepo.read_file, wrepo.ls_files())
                changed = set(rep.changed_files)
                own = sorted(
                    n
                    for n, tgt in graph.tests.items()
                    if tgt in graph.targets and graph.targets[tgt].sources & changed
                )
                if rep.mode == "full":
                    missing: list[str] = []
                else:
                    missing = [n for n in own if n not in set(rep.tests)]
                rec["own_source_tests"] = len(own)
                rec["recall_missing"] = missing
                rec["recall_ok"] = not missing
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {e}"
            rec["elapsed_s"] = round(time.monotonic() - t0, 3)
            results.append(rec)
            if (i + 1) % 25 == 0:
                print(f"{i + 1}/{len(merges)} {time.monotonic() - t_all:.0f}s", file=sys.stderr)
    finally:
        main_repo.run("worktree", "remove", "--force", str(wt), check=False)
        main_repo.run("worktree", "prune", check=False)
    total_s = time.monotonic() - t_all

    ok = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    modes = Counter(r["mode"] for r in ok)
    hand = Counter(r["hand_scope"] for r in ok)
    table: Counter[tuple[str, str]] = Counter((r["mode"], r["hand_scope"]) for r in ok)
    subs = [r for r in ok if r["mode"] == "subset" and r["total_tests"]]
    fracs = [r["n_selected"] / r["total_tests"] for r in subs]
    le50 = [
        r
        for r in ok
        if r["mode"] == "none"
        or (r["mode"] == "subset" and r["total_tests"] and r["n_selected"] <= 0.5 * r["total_tests"])
    ]
    top = sorted(subs, key=lambda r: -r["n_selected"])[:10]
    recall_fail = [r for r in ok if not r["recall_ok"]]
    agg = {
        "prs": len(results),
        "errors": len(errs),
        "modes": dict(modes),
        "subset_fraction_mean": statistics.mean(fracs) if fracs else None,
        "subset_fraction_median": statistics.median(fracs) if fracs else None,
        "share_le_50pct_incl_none": len(le50) / len(ok) if ok else None,
        "hand_scope": dict(hand),
        "mode_x_hand": {f"{m}|{h}": c for (m, h), c in sorted(table.items())},
        "recall_ok": len(ok) - len(recall_fail),
        "recall_fail": len(recall_fail),
        "total_seconds": round(total_s, 1),
        "mean_select_seconds": round(statistics.mean(r["elapsed_s"] for r in ok), 3) if ok else None,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"aggregate": agg, "prs": results}, indent=1) + "\n")

    def topfiles(r: dict) -> str:
        fs = r["changed_files"]
        return ", ".join(f"`{f}`" for f in fs[:3]) + (f" (+{len(fs) - 3})" if len(fs) > 3 else "")

    L = [
        "# agentgate measurement: mesh_control_engine",
        "",
        f"Replay of `{a.base}` first-parent merges (last {len(results)} PRs), config `{Path(a.config).name}`.",
        "",
        "## Method and limits",
        "- Per PR: base = first parent, head = merge commit; working tree checked out at the merge commit.",
        '- `select_tests` runs with `remote=""`, `base=<first parent sha>`, ctest names from CMake parsing (no build).',
        "- Hand rule = Python port of `gpu_irrelevant`/`sim_only`/`test_scope`/`touches_cmake` in `scripts/ci/local_ci.sh`;",
        "  it decides on test labels (gpu/sdk/slow), agentgate on test names, so only the verdicts are compared.",
        "- No real test failure data: recall proxy only checks that tests whose own target sources changed are selected.",
        f"- Select errors: {len(errs)}. Wall time {total_s:.0f}s, mean {agg['mean_select_seconds']}s per select.",
        "",
        "## agentgate mode",
        "| mode | PRs | share |",
        "| --- | ---: | ---: |",
    ]
    for m in ("full", "subset", "none"):
        L.append(f"| {m} | {modes.get(m, 0)} | {pct(modes.get(m, 0) / max(len(ok), 1))} |")
    if fracs:
        L += [
            "",
            (
                f"Subset PRs: {len(subs)}; selected fraction mean {pct(agg['subset_fraction_mean'])}, "
                f"median {pct(agg['subset_fraction_median'])}."
            ),
            (
                f"PRs with <= 50% of tests selected (subset or none): {len(le50)}/{len(ok)} "
                f"({pct(agg['share_le_50pct_incl_none'])})."
            ),
        ]
    L += ["", "## Hand rule (local_ci.sh test_scope)", "| scope | PRs | share |", "| --- | ---: | ---: |"]
    for s in ("full", "smoke", "nongpu"):
        L.append(f"| {s} | {hand.get(s, 0)} | {pct(hand.get(s, 0) / max(len(ok), 1))} |")
    L += [
        "",
        "## agentgate mode x hand scope (PRs)",
        "| agentgate \\ hand | full | smoke | nongpu |",
        "| --- | ---: | ---: | ---: |",
    ]
    for m in ("full", "subset", "none"):
        L.append(
            f"| {m} | " + " | ".join(str(table.get((m, s), 0)) for s in ("full", "smoke", "nongpu")) + " |"
        )
    L += [
        "",
        "## Largest subset selections",
        "| PR | selected/total | changed | top files |",
        "| ---: | ---: | ---: | --- |",
    ]
    for r in top:
        L.append(f"| #{r['pr']} | {r['n_selected']}/{r['total_tests']} | {r['n_changed']} | {topfiles(r)} |")
    L += [
        "",
        "## Recall proxy",
        f"Own-source tests selected in {agg['recall_ok']}/{len(ok)} PRs; failing: {len(recall_fail)}.",
    ]
    for r in recall_fail[:10]:
        L.append(f"- #{r['pr']}: missing {', '.join(r['recall_missing'][:5])}")
    Path(a.md).write_text("\n".join(L) + "\n")
    print(json.dumps(agg, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
