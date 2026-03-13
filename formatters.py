from typing import Any, Dict, List, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _fmt_num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _build_contract_table(title: str, contracts: List[Dict[str, Any]]) -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("Type")
    table.add_column("Expiry")
    table.add_column("Strike", justify="right")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("IV", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Gamma", justify="right")
    table.add_column("Theta", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")

    for c in contracts:
        table.add_row(
            c.get("option_type", "-").upper(),
            str(c.get("expiry_date", "-")),
            _fmt_num(c.get("strike")),
            _fmt_num(c.get("bid")),
            _fmt_num(c.get("ask")),
            _fmt_num((c.get("iv") or 0) * 100, 1) + "%" if c.get("iv") is not None else "-",
            _fmt_num(c.get("delta"), 3),
            _fmt_num(c.get("gamma"), 4),
            _fmt_num(c.get("theta"), 3),
            str(c.get("volume", 0)),
            str(c.get("open_interest", 0)),
        )
    return table


def render_option_chain(data: Dict[str, Any]):
    calls = data.get("calls", [])[:20]
    puts = data.get("puts", [])[:20]
    calls_table = _build_contract_table(f"{data.get('ticker')} Calls ({len(calls)} shown)", calls)
    puts_table = _build_contract_table(f"{data.get('ticker')} Puts ({len(puts)} shown)", puts)
    note = Text(data.get("note", ""))
    return [calls_table, puts_table, Panel(note, title="Notes")]


def render_screened_options(data: Dict[str, Any]):
    rows = data.get("results", [])[:25]
    table = Table(title=f"{data.get('ticker')} Screened {data.get('option_type', '').upper()} ({len(rows)} shown)")
    table.add_column("Expiry")
    table.add_column("Strike", justify="right")
    table.add_column("Strike %", justify="right")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Mid", justify="right")
    table.add_column("IV", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Yield %", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")

    for c in rows:
        table.add_row(
            str(c.get("expiry_date", "-")),
            _fmt_num(c.get("strike")),
            _fmt_num(c.get("strike_pct_of_spot"), 1),
            _fmt_num(c.get("bid")),
            _fmt_num(c.get("ask")),
            _fmt_num(c.get("mid")),
            _fmt_num((c.get("iv") or 0) * 100, 1) + "%" if c.get("iv") is not None else "-",
            _fmt_num(c.get("delta"), 3),
            _fmt_num(c.get("premium_yield_pct"), 3),
            str(c.get("volume", 0)),
            str(c.get("open_interest", 0)),
        )

    return [table, Panel(Text(data.get("note", "")), title="Notes")]


def render_current_price(data: Dict[str, Any]):
    table = Table(title=f"{data.get('ticker')} Snapshot")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Name", str(data.get("long_name", "-")))
    table.add_row("Price", str(data.get("current_price", "-")))
    table.add_row("Currency", str(data.get("currency", "-")))
    table.add_row("Exchange", str(data.get("exchange", "-")))
    table.add_row("Sector", str(data.get("sector", "-")))
    table.add_row("Market Cap", str(data.get("market_cap", "-")))
    table.add_row("52W High", str(data.get("fifty_two_week_high", "-")))
    table.add_row("52W Low", str(data.get("fifty_two_week_low", "-")))
    return [table]


def render_expiry_dates(data: Dict[str, Any]):
    dates = data.get("expiry_dates", [])
    table = Table(title=f"{data.get('ticker')} Expiry Dates ({len(dates)})")
    table.add_column("Expiry")
    for d in dates:
        table.add_row(str(d))
    return [table]


def render_iv_rank(data: Dict[str, Any]):
    table = Table(title=f"{data.get('ticker')} IV Rank")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Current IV", _fmt_num((data.get("current_iv") or 0) * 100, 2) + "%")
    table.add_row("52W Low", _fmt_num((data.get("iv_52w_low") or 0) * 100, 2) + "%")
    table.add_row("52W High", _fmt_num((data.get("iv_52w_high") or 0) * 100, 2) + "%")
    table.add_row("IV Rank", _fmt_num(data.get("iv_rank_pct"), 2) + "%")
    note = Panel(Text(data.get("note", "")), title="Notes")
    return [table, note]


def render_tool_result(tool_name: str, data: Dict[str, Any]):
    if "error" in data:
        return [Panel(Text(str(data["error"])), title=f"{tool_name} error")]

    if tool_name == "get_option_chain":
        return render_option_chain(data)
    if tool_name == "screen_options":
        return render_screened_options(data)
    if tool_name == "get_current_price":
        return render_current_price(data)
    if tool_name == "get_expiry_dates":
        return render_expiry_dates(data)
    if tool_name == "get_iv_rank":
        return render_iv_rank(data)

    return [Panel(Text(str(data)), title=tool_name)]
