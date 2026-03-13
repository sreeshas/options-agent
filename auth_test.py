import os
from pathlib import Path

# load .env.local
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

resp = client.get_quote("TSLA")
print(resp.json())
