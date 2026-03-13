# Options Agent

Terminal-based options analysis assistant with Schwab market data and selectable LLM support.

## What It Does

- Chooses `Anthropic` or `OpenAI` at startup
- Pulls option chains, expiry calendars, spot prices, screened contracts, and IV rank
- Uses Schwab as the market data source
- Renders tool output in a readable terminal UI with Rich

## Requirements

- Python 3.12+
- Schwab developer credentials
- At least one LLM API key
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local
```

Fill in `.env.local` with:

- `SCHWAB_API_KEY`
- `SCHWAB_APP_SECRET`
- one of `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

Optional settings:

- `SCHWAB_CALLBACK_URL`
- `SCHWAB_TOKEN_PATH`

If `SCHWAB_TOKEN_PATH` is unset, token storage defaults to a file in your home directory instead of the repository.

## Run

```bash
python main.py
```

Startup options:

- `1` for Anthropic
- `2` for OpenAI using `gpt-5-mini`

## Repo Hygiene

- Keep secrets in `.env.local`
- Do not commit token files
- `.gitignore` excludes local env files, virtualenvs, caches, editor settings, and Schwab token files

## License

MIT. See [LICENSE](/Users/sreenidhisreesha/options-agent/LICENSE).
