"""Command line: ``agentgate conflicts`` and ``agentgate select``.

Exit codes: 0 = clean, 1 = finding (conflicts found), 2 = usage/runtime error.
``--format`` picks json | markdown | args (args = what the test runner takes, select only).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config
from .git import GitError, find_repo


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo", type=Path, default=None, help="repository path (default: cwd)")
    p.add_argument(
        "--config", type=Path, default=None, help="agentgate.toml (default: <repo>/agentgate.toml)"
    )
    p.add_argument("--base", default=None, help="base branch, overrides the config (e.g. main)")
    p.add_argument("--format", choices=["json", "markdown", "args"], default="markdown")
    p.add_argument("--output", type=Path, default=None, help="also write the report (json) here")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="agentgate", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=f"agentgate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("conflicts", help="predict merge conflicts between open agent branches")
    _add_common(c)
    c.add_argument("--head", default=None, help="only pairs involving this branch (default: all pairs)")
    c.add_argument("--pattern", action="append", default=None, help="agent branch glob (repeatable)")
    c.add_argument("--fail-on-conflict", action="store_true", help="exit 1 when any pair conflicts")

    s = sub.add_parser("select", help="select the tests affected by the change since the base")
    _add_common(s)
    s.add_argument("--head", default="HEAD")
    s.add_argument("--untracked", action="store_true", help="include untracked files as changed")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = find_repo(args.repo)
        cfg = config.load(args.config or repo.root)
        if args.base:
            cfg.base = args.base
        if args.cmd == "conflicts":
            from .conflicts import forecast

            report = forecast(repo, cfg, head=args.head, patterns=args.pattern)
            text = report.to_json() if args.format == "json" else report.to_markdown()
            rc = 1 if (args.fail_on_conflict and report.conflicting) else 0
        else:
            from .select import select_tests

            report = select_tests(repo, cfg, head=args.head, include_untracked=args.untracked)
            if args.format == "json":
                text = report.to_json()
            elif args.format == "args":
                text = report.runner_args()
            else:
                text = report.to_markdown()
            rc = 0
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report.to_json())
        return rc
    except GitError as e:
        print(f"agentgate: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
