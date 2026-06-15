<!--
Thanks for contributing to MNEMA! Keep PRs focused. See CONTRIBUTING.md for the full
quality gate and conventions. Conventional-commit titles, please: feat / fix / docs /
test / chore / refactor.
-->

## What & why

<!-- What does this change and why? Link the issue it closes. -->

Closes #

## Type of change

- [ ] `fix` — bug fix (no API change)
- [ ] `feat` — new capability
- [ ] `feat` (adapter) — new backend behind an existing Protocol
- [ ] `docs` / `test` / `chore` / `refactor`

## Quality gate

Paste the output (or confirm each is green). CI runs exactly these — see CONTRIBUTING.md.

```
uv run --extra dev pytest -q                 # hermetic suite — green
uv run --extra dev --extra cloud pyright     # 0 errors
uv run --extra dev ruff check src/ tests/    # clean
```

- [ ] Hermetic test suite is green
- [ ] `pyright` reports 0 errors (ran with `--extra cloud` so SDK types resolve)
- [ ] `ruff check` is clean

## Safety covenant

The protected-fact and supersession guarantees are the product, not negotiable test details.

- [ ] I did **not** weaken a safety assertion to make a test pass.
- [ ] No hard-deletes were introduced — eviction stays recoverable (`valid_until` + cold-storage archive + audit entry).
- [ ] Consolidation still never clears the `protected` flag.
- [ ] Credentials remain `SecretStr` (never logged, never in `__repr__`/exceptions).

## New adapter? (delete if N/A)

- [ ] Implements the existing `Protocol` by structure (no inheritance).
- [ ] Heavy/cloud deps are behind the `cloud` extra and imported lazily.
- [ ] Registered in the conformance suite (`tests/conformance/conftest.py`); it passes the shared safety contract (scope isolation, protected-record survival, non-destructive eviction).
- [ ] Wired into `build_engine()` in `src/mnema/config.py` (if config-selectable).
