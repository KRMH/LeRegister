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
| `LEREGISTER_DB_PATH` | no | `~/.leregister/leregister.db` | SQLite database file. Keep it outside the repository |
| `LEREGISTER_LLM_API_KEY` | no | | Groq API key. Without it, free text is off and the Bot behaves as before |
| `LEREGISTER_LLM_PROVIDER` | no | `groq` | Only `groq` is supported for now |
| `LEREGISTER_LLM_MODEL` | no | `openai/gpt-oss-20b` | Groq model id. Pick one your account can use (list them at console.groq.com/docs/models) |
| `LEREGISTER_LLM_TIMEOUT` | no | 8 | Seconds to wait for the model |

## Free text (optional)

Write a booking in plain words, for example `chalet 2 for Sam from the 12th to the 15th of december, +96171123456`. The Bot shows the strict command it understood and records nothing; you send that command to record it.

Setup, once:

1. Create a Groq account and an API key at console.groq.com.
2. In the Groq console, open Data Controls and turn on Zero Data Retention. The Bot cannot check this for you.
3. Add `LEREGISTER_LLM_API_KEY=...` to your `.env` and restart the Bot.

The model never sees the phone number: it is replaced by a placeholder before sending and put back locally. A message that also contains other long digit runs (a number without `+`, or a date with a year) is refused instead of sent. The model does see the rest of your message: the guest name, the dates and any other words you wrote. A message that starts with `New` is always treated as a strict command and never sent.

Use a separate bot token for development and tests.

## Test

```
uv run pytest
uv run lint-imports
```
