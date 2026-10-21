"""Result types shared by the commands, with JSON and Markdown renderings.

The CLI prints one of these; the GitHub Action writes the Markdown to the step summary / PR comment
and the JSON to an output file. Keep the schema stable: it is the product's public interface.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ConflictPair:
    a: str
    b: str
    files: list[str]  # files with a content conflict
    kind: str = "content"  # content | rename | delete | unknown


@dataclass
class ConflictReport:
    base: str
    head: str | None
    branches: list[str]
    pairs: list[ConflictPair]  # branch-vs-branch, both previewed on top of the base
    base_conflicts: list[ConflictPair] = field(default_factory=list)  # branch-vs-base: needs a rebase
    merge_order: list[str] = field(default_factory=list)  # suggested order, least entangled first
    errors: list[str] = field(default_factory=list)

    @property
    def conflicting(self) -> bool:
        return bool(self.pairs) or bool(self.base_conflicts)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_markdown(self) -> str:
        lines = ["## agentgate: conflict forecast", ""]
        scope = f"`{self.head}` against" if self.head else "all pairs among"
        lines.append(f"{scope} {len(self.branches)} open agent branch(es), base `{self.base}`.")
        lines.append("")
        if self.base_conflicts:
            lines.append(
                f"**Behind the base and conflicting with it** ({len(self.base_conflicts)}): rebase first."
            )
            lines.append("")
            lines.append("| Branch | Conflicting files |")
            lines.append("| --- | --- |")
            for p in self.base_conflicts:
                files = ", ".join(f"`{f}`" for f in p.files[:6]) + (" …" if len(p.files) > 6 else "")
                lines.append(f"| `{p.a}` | {files} |")
            lines.append("")
        clean = len(self.branches) - len(self.base_conflicts)
        if not self.pairs:
            lines.append(
                f"No pair among the {clean} branch(es) that merge cleanly onto the base conflicts with another."
            )
        else:
            lines.append(
                f"**Pairs that conflict with each other** ({len(self.pairs)}), previewed on top of the base:"
            )
            lines.append("")
            lines.append("| Branch A | Branch B | Conflicting files |")
            lines.append("| --- | --- | --- |")
            for p in self.pairs:
                files = ", ".join(f"`{f}`" for f in p.files[:6]) + (" …" if len(p.files) > 6 else "")
                lines.append(f"| `{p.a}` | `{p.b}` | {files} |")
            if self.merge_order:
                lines.append("")
                lines.append("Suggested merge order: " + " → ".join(f"`{b}`" for b in self.merge_order))
        if self.errors:
            lines.append("")
            lines.append("Warnings: " + "; ".join(self.errors))
        return "\n".join(lines) + "\n"


@dataclass
class SelectionReason:
    test: str
    why: str  # "always" | "map:<glob>" | "dep:<file>" | "history:<file>" | "test-file"


@dataclass
class SelectionReport:
    base: str
    head: str
    changed_files: list[str]
    mode: str  # "full" | "subset" | "none"
    tests: list[str]  # selected test identifiers (names, regexes or paths depending on runner)
    total_tests: int | None
    reasons: list[SelectionReason] = field(default_factory=list)
    runner: str = "command"
    full_reason: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_markdown(self) -> str:
        lines = ["## agentgate: test selection", ""]
        lines.append(f"{len(self.changed_files)} changed file(s) since `{self.base}`.")
        if self.mode == "full":
            lines.append(f"Running the **full suite**: {self.full_reason or 'selection not possible'}.")
        elif self.mode == "none":
            lines.append("No tests affected (documentation-only or ignored paths).")
        else:
            total = f" of {self.total_tests}" if self.total_tests else ""
            lines.append(f"Selected **{len(self.tests)}{total}** test(s).")
            lines.append("")
            lines.append("| Test | Why |")
            lines.append("| --- | --- |")
            for r in self.reasons[:60]:
                lines.append(f"| `{r.test}` | {r.why} |")
            if len(self.reasons) > 60:
                lines.append(f"| … | {len(self.reasons) - 60} more |")
        return "\n".join(lines) + "\n"

    def runner_args(self) -> str:
        """The argument string a runner needs: a ctest -R regex, pytest paths, or newline-separated names."""
        if self.mode == "full":
            return ""
        if self.runner == "ctest":
            return "^(" + "|".join(self.tests) + ")$" if self.tests else "^$"
        if self.runner == "pytest":
            return " ".join(self.tests)
        return "\n".join(self.tests)
