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

## Example Conversations

### Covered Call Scan

Prompt:

```text
good covered call strikes for TSLA expiring in 30-45 days?
```

What the agent did:

- pulled the current TSLA spot price
- fetched available expirations
- checked IV rank
- screened calls in the target DTE window
- ranked candidate strikes in the preferred covered-call delta range

Condensed result:

```text
Short answer: IV rank was low at 21.6%, so premium was relatively cheap.

TSLA spot: $395.01

Suggested covered calls:
- 2026-04-17 435C: delta 0.268, mid 8.40, annualized yield 22.2%
- 2026-04-17 440C: delta 0.241, mid 7.28, annualized yield 19.2%
- 2026-04-17 450C: delta 0.192, mid 5.43, annualized yield 14.3%
- 2026-04-24 460C: delta 0.204, mid 6.95, annualized yield 15.3%

Trade read:
- 435C / 440C for higher income with more assignment risk
- 450C / 460C for more upside retention
- low IV rank means selling premium is less attractive than in a richer IV environment
```

### Cash-Secured Put Scan

Prompt:

```text
Is ADBE a good stock to sell cash-secured puts on after earnings?
```

What the agent did:

- pulled the current ADBE spot price
- checked current ATM IV and IV rank
- used the post-earnings context to frame the risk
- screened 30-60 DTE puts in the 5-15% OTM range
- ranked strikes by assignment risk, breakeven, and yield

Condensed result:

```text
Short answer: possibly, but IV rank was low at 21.6%, so premium was not especially rich.

ADBE spot: $269.78

Suggested cash-secured puts:
- 2026-04-17 255P: delta -0.329, mid 10.38, breakeven 244.62, annualized yield 40.1%
- 2026-04-17 250P: delta -0.288, mid 8.68, breakeven 241.32, annualized yield 33.6%
- 2026-04-17 245P: delta -0.249, mid 7.25, breakeven 237.75, annualized yield 28.0%
- 2026-04-17 240P: delta -0.214, mid 6.00, breakeven 234.00, annualized yield 23.2%
- 2026-04-17 230P: delta -0.153, mid 4.00, breakeven 226.00, annualized yield 15.5%

Trade read:
- 255P / 250P for more premium and higher assignment probability
- 245P / 240P for a more balanced short-put setup
- 230P for a more conservative entry with less premium
- low IV rank means it may be better to wait if you do not actually want to own the shares
```

### IV Rank Lookup

Prompt:

```text
whats the IV rank for nvda now?
```

What the agent did:

- fetched NVDA ATM implied volatility
- compared it against the 1-year historical volatility proxy range
- returned the current IV rank with a short interpretation

Condensed result:

```text
NVDA IV rank: 14.7%
Current ATM IV: 42.8%
52-week low: 8.9%
52-week high: 240.0%

Interpretation:
IV rank is low, so option premium is relatively cheap versus the past year.
That is generally less attractive for premium selling unless you have a specific stock-entry or hedging reason.
```

### Full Chain Lookup

Prompt:

```text
can i get full option chain for tsla for july 2027 expiry
```

What the agent did:

- fetched available TSLA expirations
- noticed that July 2027 was not listed
- suggested the nearest valid expiries instead of failing
- pulled the 2027-06-17 chain after follow-up confirmation
- narrowed the display to ATM +/- 10 strikes for readability

Condensed result:

```text
Requested expiry was not available.
Nearest long-dated TSLA expiries:
- 2027-06-17
- 2027-12-17

After selecting 2027-06-17, the agent returned an ATM +/- 10 strikes view.

Spot: $395.01
Expiry: 2027-06-17
DTE: 461

Sample rows near ATM:
- 390C: bid 99.80, ask 101.05, delta 0.614, IV 45.81%
- 400C: bid 95.70, ask 96.25, delta 0.595, IV 45.55%
- 410C: bid 91.40, ask 92.70, delta 0.575, IV 45.35%
- 390P: bid 76.45, ask 77.05, delta -0.386, IV 45.81%
- 400P: bid 81.95, ask 82.60, delta -0.405, IV 45.55%
- 410P: bid 87.65, ask 88.50, delta -0.424, IV 45.35%

Trade read:
- the agent can recover gracefully when an exact expiry is unavailable
- long-dated chains are large, so filtered views are more practical than dumping every strike
- ATM and near-ATM long-dated TSLA options carried high deltas and mid-40s to mid-50s IV in this snapshot
```

## Repo Hygiene

- Keep secrets in `.env.local`
- Do not commit token files
- `.gitignore` excludes local env files, virtualenvs, caches, editor settings, and Schwab token files

## License

MIT. See [LICENSE](/Users/sreenidhisreesha/options-agent/LICENSE).
