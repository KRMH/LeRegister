# LeRegister

Telegram bot that records phone bookings for one Owner. See `_bmad-output/planning-artifacts/` for the PRD, architecture and epics.

## Run

```
uv sync
uv run leregister
```

The bot uses long polling and opens no inbound port.

## Settings

Set as environment variables, or in a `.env` file. The default `.env` location is `~/.leregister/.env`, outside the repository. Override it with `LEREGISTER_ENV_FILE`. Real environment variables win over the file.

| Setting | Required | Default | Meaning |
| --- | --- | --- | --- |
| `LEREGISTER_BOT_TOKEN` | yes | | Telegram bot token from @BotFather |
| `LEREGISTER_OWNER_ID` | yes | | Owner's numeric Telegram user id. Only this account is answered |
| `LEREGISTER_CHALET_COUNT` | no | 40 | Number of chalets |
| `LEREGISTER_MAX_STAY` | no | 60 | Maximum stay in nights |

Use a separate bot token for development and tests.

## Test

```
uv run pytest
uv run lint-imports
```
