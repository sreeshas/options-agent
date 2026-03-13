import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from system_prompt import build_system_prompt
from tools import TOOL_SCHEMAS, call_tool

ANTHROPIC_MODEL_NAME = "claude-sonnet-4-20250514"
OPENAI_MODEL_NAME = "gpt-5-mini"
SUPPORTED_LLM_PROVIDERS = {"anthropic", "openai"}


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


@dataclass
class ToolEvent:
    tool_name: str
    result: Dict[str, Any]


@dataclass
class AgentResponse:
    text: str
    tool_events: List[ToolEvent]


class BaseLLMBackend(ABC):
    @abstractmethod
    def run_turn(self, user_input: str) -> AgentResponse:
        raise NotImplementedError


class AnthropicBackend(BaseLLMBackend):
    def __init__(self, api_key: str, model_name: str = ANTHROPIC_MODEL_NAME) -> None:
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model_name = model_name
        self.messages: List[Dict[str, Any]] = []

    @staticmethod
    def _serialize_blocks(blocks: List[Any]) -> List[Dict[str, Any]]:
        serialized = []
        for block in blocks:
            if block.type == "text":
                serialized.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                serialized.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return serialized

    def run_turn(self, user_input: str) -> AgentResponse:
        self.messages.append({"role": "user", "content": user_input})
        tool_events: List[ToolEvent] = []

        while True:
            response = self.client.messages.create(
                model=self.model_name,
                system=build_system_prompt(),
                max_tokens=1800,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )

            serialized_blocks = self._serialize_blocks(response.content)
            self.messages.append({"role": "assistant", "content": serialized_blocks})

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                final_text = "\n".join(block.text for block in response.content if block.type == "text").strip()
                return AgentResponse(text=final_text, tool_events=tool_events)

            tool_results_payload = []
            for tool_use in tool_uses:
                result = _execute_tool(tool_use.name, tool_use.input)
                tool_events.append(ToolEvent(tool_name=tool_use.name, result=result))
                tool_results_payload.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            self.messages.append({"role": "user", "content": tool_results_payload})


class OpenAIBackend(BaseLLMBackend):
    def __init__(self, api_key: str, model_name: str = OPENAI_MODEL_NAME) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.previous_response_id: Optional[str] = None

    @staticmethod
    def _tool_definitions() -> List[Dict[str, Any]]:
        definitions: List[Dict[str, Any]] = []
        for schema in TOOL_SCHEMAS:
            definitions.append(
                {
                    "type": "function",
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["input_schema"],
                }
            )
        return definitions

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        text_parts: List[str] = []
        output = getattr(response, "output", []) or []
        for item in output:
            if getattr(item, "type", None) == "message":
                for content in getattr(item, "content", []) or []:
                    content_type = getattr(content, "type", None)
                    if content_type in {"output_text", "text"}:
                        text_value = getattr(content, "text", None)
                        if text_value:
                            text_parts.append(text_value)
        if text_parts:
            return "\n".join(text_parts).strip()
        return (getattr(response, "output_text", "") or "").strip()

    def run_turn(self, user_input: str) -> AgentResponse:
        pending_input: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}],
            }
        ]
        tool_events: List[ToolEvent] = []

        while True:
            request_args: Dict[str, Any] = {
                "model": self.model_name,
                "instructions": build_system_prompt(),
                "input": pending_input,
                "tools": self._tool_definitions(),
            }
            if self.previous_response_id:
                request_args["previous_response_id"] = self.previous_response_id

            response = self.client.responses.create(**request_args)
            self.previous_response_id = getattr(response, "id", None)

            function_calls = []
            for item in getattr(response, "output", []) or []:
                item_type = getattr(item, "type", None)
                if item_type in {"function_call", "tool_call"}:
                    function_calls.append(item)

            if not function_calls:
                return AgentResponse(text=self._extract_output_text(response), tool_events=tool_events)

            tool_results_payload = []
            for function_call in function_calls:
                tool_name = getattr(function_call, "name", None)
                arguments = getattr(function_call, "arguments", "{}")
                call_id = getattr(function_call, "call_id", None) or getattr(function_call, "id", None)
                try:
                    tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError as err:
                    result = {"error": f"Invalid tool arguments: {err}"}
                else:
                    result = _execute_tool(tool_name, tool_input)

                tool_events.append(ToolEvent(tool_name=tool_name or "unknown", result=result))
                tool_results_payload.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result, default=str),
                    }
                )

            pending_input = tool_results_payload


def _execute_tool(tool_name: Optional[str], tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not tool_name:
            raise ValueError("Tool call missing name.")
        return call_tool(tool_name, tool_input)
    except Exception as err:
        return {"error": str(err), "tool_name": tool_name}


class OptionsAgent:
    def __init__(self, provider: str = "anthropic") -> None:
        _load_env_local()
        selected_provider = provider.lower().strip()
        if selected_provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}."
            )

        self.provider = selected_provider
        self.backend = self._build_backend(selected_provider)

    @staticmethod
    def _build_backend(provider: str) -> BaseLLMBackend:
        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. Add it to options-agent/.env.local or export it in your shell."
                )
            return AnthropicBackend(api_key=api_key)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to options-agent/.env.local or export it in your shell."
            )
        return OpenAIBackend(api_key=api_key)

    def run(self, user_input: str) -> AgentResponse:
        return self.backend.run_turn(user_input)
