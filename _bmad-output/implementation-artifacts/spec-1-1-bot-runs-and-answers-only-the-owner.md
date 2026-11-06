---
title: '1.1 Bot runs and answers only the Owner'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: 'faafa9b07f552273afb05ee06b830faf5f973491'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** There is no code yet. The Owner needs a Telegram bot that answers only them, on a scaffold that enforces the hexagonal rule (pure `core`) from the first commit.

**Approach:** Create the `uv` Python 3.11 project with the pinned stack and layout `src/leregister/{core,adapters/telegram,app.py}`. Add settings loading and a long-polling bot that gates every update on the Owner id and a private chat, and replies with a temporary "LeRegister is running". Add an `import-linter` contract and tests.

## Boundaries & Constraints

**Always:** `core` imports no adapter, Telegram, SQLite, Trello or HTTP library, and gets time only through a `Clock` port. The Owner gate runs before anything else and drops other updates silently. Logs carry ids only, never names or phones. Settings come from the environment, with `.env` as a fallback. The default `.env` path sits outside the repo and is overridable by `LEREGISTER_ENV_FILE`. Required: bot token and Owner Telegram id. Optional: chalet count (default 40) and max stay (default 60). A missing or non-numeric required setting stops startup with a clear message naming it. Python 3.11.9 and versions pinned per AR17.

**Never:** No inbound port or webhook. No database, parser, outbox or journal (Stories 1.2-1.5). No changing the Owner id via chat. Do not log message text. Add no dependency beyond AR17 (no python-dotenv; parse `.env` with the stdlib).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Owner private message | Update from Owner id, private chat | Reply "LeRegister is running" | N/A |
| Other account | Private message, different user id | No reply, no state change | Log user id only |
| Group chat | Owner id, chat type group | No reply | Log chat id only |
| Update without user or message | e.g. channel post | Ignored | N/A |
| Missing setting | Token or Owner id absent or invalid | Process exits non-zero with message naming the setting | No Telegram connection attempted |
| Owner id changed | Restart with new id | Only the new id accepted | N/A |

</frozen-after-approval>

## Code Map

- `pyproject.toml` -- greenfield; new. `uv` project, `requires-python = "==3.11.*"`, `src` layout, pinned deps, import-linter config
- `src/leregister/core/ports.py` -- new. `Clock` Protocol only. Core must not import Telegram.
- `src/leregister/core/access.py` -- new. Pure `is_owner(user_id, chat_type, owner_id)` decision
- `src/leregister/adapters/telegram/bot.py` -- new. Builds the application, gates updates, replies
- `src/leregister/config.py` -- new. `Settings` dataclass, `.env` stdlib loader, `ConfigError`
- `src/leregister/app.py` -- new. `main()` wires config → bot, runs `run_polling`, exits 2 on `ConfigError`
- `tests/` -- new. Boundary tests with fake updates; no network or real token

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` -- `uv init` project, add pinned deps and dev deps (pytest, import-linter), `[tool.importlinter]` forbidden contract for `core` -- AR1, AR17
- [x] `src/leregister/core/{__init__,ports,access}.py` -- `Clock` port and `is_owner` pure function -- keeps the gate rule in core (AD-1, AD-6)
- [x] `src/leregister/config.py` -- `Settings.load(env)` with required/optional keys and defaults, `.env` fallback -- AR16
- [x] `src/leregister/adapters/telegram/bot.py` -- handler for all message updates; calls `is_owner`; replies plain text only on pass -- AD-6
- [x] `src/leregister/app.py` + `[project.scripts] leregister` -- entrypoint -- AR14
- [x] `tests/test_import_contract.py` -- run `lint-imports` on the real contract and again on a temp copy with a forbidden import to prove it fails -- AC1
- [x] `tests/test_config.py`, `tests/test_owner_gate.py` -- the I/O matrix rows, using fake updates -- AC2-5
- [x] `README.md` -- run instructions and settings table -- AR16

**Acceptance Criteria:**
- Given the test suite, when run, then the import-linter contract passes and fails if `core` imports an adapter, Telegram, sqlite3 or httpx.
- Given valid settings, when the Bot starts, then it long-polls and opens no listening socket.
- Given a missing required setting, when the Bot starts, then it exits non-zero with a message naming the setting.
- Given a non-Owner or group message, when it arrives, then no reply is sent and no data changes.

## Verification

**Commands:**
- `uv sync` -- expected: environment resolves on Python 3.11
- `uv run pytest` -- expected: all tests pass
- `uv run lint-imports` -- expected: contract kept

**Manual checks (if no CLI):**
- With a throwaway bot token, send a message from the Owner account and then from another account: only the first gets "LeRegister is running".
