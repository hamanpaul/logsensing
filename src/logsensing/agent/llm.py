"""LLM 客戶端 — OpenAI 相容 API."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openai import OpenAI


class LLMClient:
    """OpenAI-compatible LLM client with function calling support."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        kwargs: dict[str, Any] = {}
        if api_base:
            kwargs["base_url"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        else:
            # Allow dummy key for local/self-hosted endpoints
            kwargs["api_key"] = "not-set"

        self._client = OpenAI(**kwargs)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._tools: list[dict[str, Any]] = []
        self._tool_handlers: dict[str, Callable[..., str]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., str],
    ) -> None:
        """Register a function calling tool."""
        self._tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
        self._tool_handlers[name] = handler

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        """Send messages and handle tool calls automatically. Returns final text response."""
        full_messages: list[dict[str, Any]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Loop to handle tool calls (max 5 rounds)
        for _ in range(5):
            call_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": full_messages,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            }
            if self._tools:
                call_kwargs["tools"] = self._tools
                call_kwargs["tool_choice"] = "auto"

            response = self._client.chat.completions.create(**call_kwargs)
            choice = response.choices[0]
            message = choice.message

            if not message.tool_calls:
                return message.content or ""

            # Process tool calls
            full_messages.append(message.model_dump())
            for tc in message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                handler = self._tool_handlers.get(fn_name)
                result = handler(**fn_args) if handler else f"Error: unknown tool {fn_name}"
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        return message.content or ""  # type: ignore[possibly-undefined]

    @property
    def model(self) -> str:
        return self._model
