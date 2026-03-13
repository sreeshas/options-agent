import os
import json
import datetime
from pathlib import Path

# Load .env.local
env_path = Path(__file__).resolve().parent / ".env.local"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

from schwab import auth

client = auth.easy_client(
    api_key=os.getenv("SCHWAB_API_KEY"),
    app_secret=os.getenv("SCHWAB_APP_SECRET"),
    callback_url=os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/"),
    token_path=os.getenv("SCHWAB_TOKEN_PATH", str(Path.home() / ".schwab_token.json")),
)

resp = client.get_option_chain(
    "TSLA",
    from_date=datetime.date(2026, 7, 17),
    to_date=datetime.date(2026, 7, 17),
    include_underlying_quote=True
)

data = resp.json()

# Pull first call contract and print it so we can see all fields
call_map = data.get("callExpDateMap", {})
for expiry, strikes in call_map.items():
    for strike, contracts in strikes.items():
        contract = contracts[0]
        print(f"\nExpiry: {expiry}  Strike: {strike}")
        print(json.dumps(contract, indent=2))
        break  # just show the first strike
    break  # just show the first expiry
