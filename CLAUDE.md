# Working in agentgate

- Pure Python 3.11+, standard library only at runtime (`pyproject.toml` has no dependencies; keep it so).
- Every git call goes through `agentgate.git.Repo`; never call `subprocess` elsewhere.
- Public interface = the JSON schema of `report.py` and the CLI flags in `cli.py`. Changing either is a
  breaking change: note it in the commit message.
- Each module's docstring states its contract; implement to it, and add a test per rule in the contract.
- Tests use the `sandbox` fixture (a throwaway git repo); never test against a real remote.
- Before committing: `ruff check src tests && python3 -m pytest -q`.
- Commit messages in English, imperative, one line + optional body.
