from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from agent import OptionsAgent
from formatters import render_tool_result


def _choose_provider(console: Console) -> str:
    console.print(
        Panel(
            "Choose your LLM provider before starting:\n"
            "1. Anthropic (`ANTHROPIC_API_KEY`)\n"
            "2. OpenAI (`OPENAI_API_KEY`, model `gpt-5-mini`)",
            title="LLM Provider",
        )
    )

    while True:
        choice = console.input("[bold cyan]Provider [1/2]: [/]").strip().lower()
        if choice in {"1", "anthropic"}:
            return "anthropic"
        if choice in {"2", "openai", "gpt", "gpt-5-mini"}:
            return "openai"
        console.print(Panel("Enter `1` for Anthropic or `2` for OpenAI.", title="Invalid Selection", style="red"))


def main() -> None:
    console = Console()
    try:
        provider = _choose_provider(console)
        agent = OptionsAgent(provider=provider)
    except Exception as err:
        console.print(Panel(str(err), title="Startup Error", style="red"))
        return

    console.print(
        Panel(
            "Options Agent is ready. Ask about covered calls, cash-secured puts, full chains, screens, and IV rank.\n"
            f"LLM provider: {agent.provider}\n"
            "Examples:\n"
            "- What are good covered call strikes for TSLA expiring in 60-90 days?\n"
            "- Show me the full options chain for AAPL expiring January 2027\n"
            "- Find puts on NVDA that are 10% OTM expiring in 30-60 days\n"
            "Type 'exit' to quit.",
            title="Options AI Agent",
        )
    )

    while True:
        try:
            user_input = console.input("[bold cyan]> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            console.print("Exiting.")
            break

        try:
            console.print(
                Panel(
                    Text(user_input, style="bold cyan"),
                    title="You",
                    border_style="cyan",
                )
            )
            console.print(Rule("[bold green]Assistant[/bold green]", style="green"))
            response = agent.run(user_input)
            for event in response.tool_events:
                for renderable in render_tool_result(event.tool_name, event.result):
                    console.print(renderable)
            if response.text:
                console.print(Markdown(response.text))
            console.print(Rule(style="dim"))
        except Exception as err:
            console.print(Panel(str(err), title="Runtime Error", style="red"))


if __name__ == "__main__":
    main()
