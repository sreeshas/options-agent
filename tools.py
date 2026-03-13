import math
import os
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

RISK_FREE_RATE = 0.04
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.5
SUPPORTED_SOURCES = ["auto", "schwab"]


TOOL_SCHEMAS = [
    {
        "name": "get_option_chain",
        "description": "Return calls and puts for a ticker/expiry with strike, bid, ask, IV, Greeks, volume, and open interest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "expiry_date": {
                    "type": "string",
                    "description": "Expiration date in YYYY-MM-DD format.",
                },
                "source": {
                    "type": "string",
                    "enum": SUPPORTED_SOURCES,
                    "description": "Data source to use. Default is auto.",
                },
            },
            "required": ["ticker", "expiry_date"],
        },
    },
    {
        "name": "get_expiry_dates",
        "description": "Return available option expiration dates for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": SUPPORTED_SOURCES,
                    "description": "Data source to use. Default is auto.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_current_price",
        "description": "Return current stock price and basic company info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": SUPPORTED_SOURCES,
                    "description": "Data source to use. Default is auto.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "screen_options",
        "description": "Filter options across expiries and strikes by DTE, strike distance, and IV; return ranked results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "option_type": {"type": "string", "enum": ["call", "put"]},
                "min_expiry_days": {"type": "integer"},
                "max_expiry_days": {"type": "integer"},
                "min_strike_pct": {"type": "number"},
                "max_strike_pct": {"type": "number"},
                "min_iv": {"type": "number"},
                "max_iv": {"type": "number"},
                "source": {
                    "type": "string",
                    "enum": SUPPORTED_SOURCES,
                    "description": "Data source to use. Default is auto.",
                },
            },
            "required": [
                "ticker",
                "option_type",
                "min_expiry_days",
                "max_expiry_days",
                "min_strike_pct",
                "max_strike_pct",
                "min_iv",
                "max_iv",
            ],
        },
    },
    {
        "name": "get_iv_rank",
        "description": "Estimate IV rank using current ATM IV and a 1-year historical-volatility proxy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": SUPPORTED_SOURCES,
                    "description": "Data source to use. Default is auto.",
                },
            },
            "required": ["ticker"],
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _with_retries(func):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return func()
        except Exception as err:
            last_err = err
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(f"Data request failed after {MAX_RETRIES} attempts: {last_err}")


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def _approx_greeks(option_type: str, spot: float, strike: float, iv: float, dte: int) -> Dict[str, Optional[float]]:
    if not spot or not strike or not iv or iv <= 0 or dte <= 0:
        return {"delta": None, "gamma": None, "theta": None}
    t = dte / 365.0
    try:
        d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
        d2 = d1 - iv * math.sqrt(t)
        if option_type == "call":
            delta = _norm_cdf(d1)
            theta = (
                            -(spot * _norm_pdf(d1) * iv) / (2 * math.sqrt(t))
                            - RISK_FREE_RATE * strike * math.exp(-RISK_FREE_RATE * t) * _norm_cdf(d2)
                    ) / 365.0
        else:
            delta = _norm_cdf(d1) - 1
            theta = (
                            -(spot * _norm_pdf(d1) * iv) / (2 * math.sqrt(t))
                            + RISK_FREE_RATE * strike * math.exp(-RISK_FREE_RATE * t) * _norm_cdf(-d2)
                    ) / 365.0
        gamma = _norm_pdf(d1) / (spot * iv * math.sqrt(t))
        return {"delta": round(delta, 4), "gamma": round(gamma, 6), "theta": round(theta, 4)}
    except (ValueError, ZeroDivisionError):
        return {"delta": None, "gamma": None, "theta": None}


def _normalize_iv(value: float) -> float:
    return value / 100.0 if value > 1.0 else value


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_env_local() -> None:
    env_path = Path(__file__).resolve().parent / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Schwab Provider
# ---------------------------------------------------------------------------

class SchwabProvider:
    name = "schwab"
    _client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        _load_env_local()
        from schwab import auth
        api_key = os.getenv("SCHWAB_API_KEY")
        app_secret = os.getenv("SCHWAB_APP_SECRET")
        token_path = os.getenv("SCHWAB_TOKEN_PATH", str(Path.home() / ".schwab_token.json"))
        callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")
        if not api_key or not app_secret:
            raise ValueError("SCHWAB_API_KEY and SCHWAB_APP_SECRET must be set.")
        self._client = auth.easy_client(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=callback_url,
            token_path=token_path,
        )
        return self._client

    def _parse_contract(self, contract: Dict, option_type: str, spot: float) -> Dict[str, Any]:
        strike = _as_float(contract.get("strikePrice")) or 0.0
        bid = _as_float(contract.get("bid")) or 0.0
        ask = _as_float(contract.get("ask")) or 0.0
        mid = round((bid + ask) / 2, 2)
        dte = int(contract.get("daysToExpiration") or 0)
        expiry_raw = contract.get("expirationDate", "")
        expiry_date = expiry_raw[:10] if expiry_raw else ""

        # Schwab IV comes as a percentage like 65.3 meaning 65.3% — normalize to decimal
        raw_iv = _as_float(contract.get("volatility"))
        iv = round(raw_iv / 100.0, 4) if raw_iv and raw_iv > 1.0 else (raw_iv or 0.0)

        delta = _as_float(contract.get("delta"))
        gamma = _as_float(contract.get("gamma"))
        theta = _as_float(contract.get("theta"))
        vega = _as_float(contract.get("vega"))

        annualized_yield = round((mid / spot) * (365 / dte) * 100, 2) if spot and dte > 0 and mid > 0 else None

        return {
            "contract_symbol": contract.get("symbol"),
            "option_type": option_type,
            "expiry_date": expiry_date,
            "days_to_expiry": dte,
            "strike": strike,
            "strike_pct_of_spot": round(strike / spot * 100, 2) if spot else None,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "iv": iv,
            "delta": round(delta, 4) if delta is not None else None,
            "gamma": round(gamma, 6) if gamma is not None else None,
            "theta": round(theta, 4) if theta is not None else None,
            "vega": round(vega, 4) if vega is not None else None,
            "volume": int(contract.get("totalVolume") or 0),
            "open_interest": int(contract.get("openInterest") or 0),
            "in_the_money": bool(contract.get("inTheMoney", False)),
            "annualized_yield_pct": annualized_yield,
            "source": "schwab",
        }

    def _fetch_chain(self, ticker: str, from_date: date, to_date: date) -> tuple:
        """Returns (spot, calls_list, puts_list)"""
        client = self._get_client()
        resp = _with_retries(lambda: client.get_option_chain(
            ticker.upper(),
            from_date=from_date,
            to_date=to_date,
            include_underlying_quote=True,
        ))
        resp.raise_for_status()
        data = resp.json()

        # Extract underlying price
        underlying = data.get("underlying") or {}
        spot = _as_float(underlying.get("mark")) or _as_float(underlying.get("last")) or 0.0

        calls: List[Dict] = []
        puts: List[Dict] = []

        for exp_key, strikes in data.get("callExpDateMap", {}).items():
            for strike_key, contracts in strikes.items():
                for c in contracts:
                    parsed = self._parse_contract(c, "call", spot)
                    calls.append(parsed)

        for exp_key, strikes in data.get("putExpDateMap", {}).items():
            for strike_key, contracts in strikes.items():
                for c in contracts:
                    parsed = self._parse_contract(c, "put", spot)
                    puts.append(parsed)

        return spot, calls, puts

    def _get_price_history_frame(self, ticker: str) -> pd.DataFrame:
        client = self._get_client()
        history_methods = [
            "get_price_history_every_day",
            "get_price_history",
        ]
        last_error: Optional[Exception] = None

        for method_name in history_methods:
            method = getattr(client, method_name, None)
            if method is None:
                continue
            try:
                if method_name == "get_price_history_every_day":
                    resp = _with_retries(lambda: method(ticker.upper(), need_extended_hours_data=False))
                else:
                    start = datetime.now(timezone.utc) - timedelta(days=370)
                    end = datetime.now(timezone.utc)
                    resp = _with_retries(
                        lambda: method(
                            ticker.upper(),
                            start_datetime=start,
                            end_datetime=end,
                            need_extended_hours_data=False,
                        )
                    )
                resp.raise_for_status()
                candles = resp.json().get("candles", [])
                if not candles:
                    continue
                frame = pd.DataFrame(candles)
                if "close" not in frame:
                    continue
                return frame
            except Exception as err:
                last_error = err

        if last_error:
            raise ValueError(f"Unable to fetch price history from Schwab: {last_error}")
        raise ValueError("Schwab client does not expose a supported price history endpoint.")

    def get_current_price(self, ticker: str) -> Dict[str, Any]:
        client = self._get_client()
        resp = _with_retries(lambda: client.get_quote(ticker.upper()))
        resp.raise_for_status()
        data = resp.json()
        quote = data.get(ticker.upper(), {}).get("quote", {})
        reference = data.get(ticker.upper(), {}).get("reference", {})
        return {
            "ticker": ticker.upper(),
            "current_price": _as_float(quote.get("mark") or quote.get("lastPrice")),
            "currency": "USD",
            "long_name": reference.get("description") or ticker.upper(),
            "sector": None,
            "market_cap": None,
            "fifty_two_week_high": _as_float(quote.get("52WeekHigh")),
            "fifty_two_week_low": _as_float(quote.get("52WeekLow")),
        }

    def get_expiry_dates(self, ticker: str) -> Dict[str, Any]:
        client = self._get_client()
        resp = _with_retries(lambda: client.get_option_expiration_chain(ticker.upper()))
        resp.raise_for_status()
        data = resp.json()
        dates = []
        for item in data.get("expirationList", []):
            exp_date = item.get("expirationDate")
            if exp_date:
                # Normalize to YYYY-MM-DD
                dates.append(str(exp_date)[:10])
        dates = sorted(set(dates))
        return {"ticker": ticker.upper(), "expiry_dates": dates, "count": len(dates)}

    def get_option_chain(self, ticker: str, expiry_date: str) -> Dict[str, Any]:
        exp = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        spot, calls, puts = self._fetch_chain(ticker, from_date=exp, to_date=exp)
        # Filter to exact expiry
        calls = [c for c in calls if c["expiry_date"] == expiry_date]
        puts = [p for p in puts if p["expiry_date"] == expiry_date]
        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])
        return {
            "ticker": ticker.upper(),
            "spot_price": spot,
            "expiry_date": expiry_date,
            "calls": calls,
            "puts": puts,
            "note": "Greeks sourced directly from Schwab feed.",
        }

    def screen_options(self, ticker, option_type, min_expiry_days, max_expiry_days,
                       min_strike_pct, max_strike_pct, min_iv, max_iv) -> Dict[str, Any]:
        today = date.today()
        from_date = today + timedelta(days=min_expiry_days)
        to_date = today + timedelta(days=max_expiry_days)
        min_iv_n = _normalize_iv(min_iv)
        max_iv_n = _normalize_iv(max_iv)

        spot, calls, puts = self._fetch_chain(ticker, from_date=from_date, to_date=to_date)
        contracts = calls if option_type == "call" else puts

        results = []
        for c in contracts:
            dte = c.get("days_to_expiry", 0)
            spct = c.get("strike_pct_of_spot")
            iv = c.get("iv", 0)
            if dte < min_expiry_days or dte > max_expiry_days:
                continue
            if spct is None or not (min_strike_pct <= spct <= max_strike_pct):
                continue
            if not (min_iv_n <= iv <= max_iv_n):
                continue
            results.append(c)

        results.sort(key=lambda x: x.get("annualized_yield_pct") or 0, reverse=True)
        return {
            "ticker": ticker.upper(),
            "spot_price": spot,
            "option_type": option_type,
            "filters": {
                "expiry_days": [min_expiry_days, max_expiry_days],
                "strike_pct": [min_strike_pct, max_strike_pct],
                "iv": [round(min_iv_n, 4), round(max_iv_n, 4)],
            },
            "count": len(results),
            "results": results[:20],
        }

    def get_iv_rank(self, ticker: str) -> Dict[str, Any]:
        # Get current IV from nearest ATM options (30-60 DTE)
        today = date.today()
        from_date = today + timedelta(days=25)
        to_date = today + timedelta(days=65)
        spot, calls, _ = self._fetch_chain(ticker, from_date=from_date, to_date=to_date)

        atm_candidates = [
            c for c in calls
            if c.get("iv") and c.get("iv") > 0 and c.get("days_to_expiry", 0) >= 25
        ]
        if not atm_candidates:
            raise ValueError("No ATM options found for IV rank calculation.")

        atm_candidates.sort(key=lambda c: abs((c.get("strike") or 0) - spot))
        current_iv = float(sum(c["iv"] for c in atm_candidates[:4]) / len(atm_candidates[:4]))

        hist = self._get_price_history_frame(ticker)
        if hist.empty or len(hist) < 30:
            raise ValueError("Not enough historical data for IV rank.")
        closes = hist["close"].tolist()
        hv = (pd.Series(closes).pct_change().rolling(20).std() * math.sqrt(252)).dropna()
        iv_low = float(hv.min())
        iv_high = float(hv.max())
        iv_rank = 0.0 if iv_high <= iv_low else ((current_iv - iv_low) / (iv_high - iv_low)) * 100.0
        iv_rank = max(0.0, min(100.0, iv_rank))

        return {
            "ticker": ticker.upper(),
            "current_iv": round(current_iv, 4),
            "iv_52w_low": round(iv_low, 4),
            "iv_52w_high": round(iv_high, 4),
            "iv_rank_pct": round(iv_rank, 2),
            "note": "Current IV from Schwab ATM options; historical range from Schwab daily-price HV proxy.",
        }


# ---------------------------------------------------------------------------
# Provider registry & routing
# ---------------------------------------------------------------------------

def _build_providers():
    _load_env_local()
    providers: Dict[str, Any] = {}
    has_schwab = bool(os.getenv("SCHWAB_API_KEY") and os.getenv("SCHWAB_APP_SECRET"))
    if has_schwab:
        providers["schwab"] = SchwabProvider()
    return providers


PROVIDERS: Dict[str, Any] = _build_providers()


def _source_order(source: Optional[str]) -> List[str]:
    requested = (source or os.getenv("OPTIONS_DATA_SOURCE", "auto") or "auto").lower().strip()
    if requested not in SUPPORTED_SOURCES:
        raise ValueError(f"Unsupported source '{requested}'. Supported: {', '.join(SUPPORTED_SOURCES)}")
    if requested == "schwab":
        return ["schwab"]
    return ["schwab"]


def _run_with_sources(method_name: str, source: Optional[str], *args, **kwargs) -> Dict[str, Any]:
    errors: List[str] = []
    for src in _source_order(source):
        provider = PROVIDERS.get(src)
        if provider is None:
            errors.append(f"{src}: provider not configured")
            continue
        try:
            result = getattr(provider, method_name)(*args, **kwargs)
            result["source"] = src
            if errors:
                result["fallback_note"] = f"Primary source failed. Used {src}. Errors: {' | '.join(errors)}"
            return result
        except Exception as err:
            errors.append(f"{src}: {err}")
    raise ValueError("All data sources failed. " + " | ".join(errors))


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def get_expiry_dates(ticker: str, source: Optional[str] = None) -> Dict[str, Any]:
    return _run_with_sources("get_expiry_dates", source, ticker)


def get_current_price(ticker: str, source: Optional[str] = None) -> Dict[str, Any]:
    return _run_with_sources("get_current_price", source, ticker)


def get_option_chain(ticker: str, expiry_date: str, source: Optional[str] = None) -> Dict[str, Any]:
    return _run_with_sources("get_option_chain", source, ticker, expiry_date)


def screen_options(
        ticker: str,
        option_type: str,
        min_expiry_days: int,
        max_expiry_days: int,
        min_strike_pct: float,
        max_strike_pct: float,
        min_iv: float,
        max_iv: float,
        source: Optional[str] = None,
) -> Dict[str, Any]:
    return _run_with_sources(
        "screen_options", source, ticker, option_type,
        min_expiry_days, max_expiry_days,
        min_strike_pct, max_strike_pct,
        min_iv, max_iv,
    )


def get_iv_rank(ticker: str, source: Optional[str] = None) -> Dict[str, Any]:
    return _run_with_sources("get_iv_rank", source, ticker)


TOOL_FUNCTIONS = {
    "get_option_chain": get_option_chain,
    "get_expiry_dates": get_expiry_dates,
    "get_current_price": get_current_price,
    "screen_options": screen_options,
    "get_iv_rank": get_iv_rank,
}


def call_tool(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOL_FUNCTIONS[name](**tool_input)
