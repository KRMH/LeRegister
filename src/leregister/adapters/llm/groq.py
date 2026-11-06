"""Groq (GroqCloud) Interpreter: one JSON-mode chat completion call, nothing else (AR20).

The OpenAI-compatible endpoint is used. Message text, model output and the API key are never logged.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from leregister.core.ports import InterpreterUnavailable

log = logging.getLogger(__name__)

URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ANSWER_TOKENS = 1500  # reasoning models spend part of this thinking before they write the JSON


class GroqInterpreter:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = client or httpx.AsyncClient()

    def __repr__(self) -> str:  # the key must never show up in a log or a traceback
        return f"GroqInterpreter(model={self._model!r})"

    async def complete(self, system: str, user: str) -> str:
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": MAX_ANSWER_TOKENS,
            "response_format": {"type": "json_object"},
        }
        if self._model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # a short thought is enough to read a booking sentence
        try:
            # httpx applies its timeout to each phase separately, so the whole call is bounded too
            response = await asyncio.wait_for(
                self._client.post(
                    URL,
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=self._timeout,
                ),
                timeout=self._timeout,
            )
        except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError, asyncio.TimeoutError) as exc:
            log.warning("interpreter request failed: %s", type(exc).__name__)
            raise InterpreterUnavailable from None
        if response.status_code != 200:
            log.warning("interpreter returned status %s", response.status_code)
            raise InterpreterUnavailable
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            log.warning("interpreter returned an unreadable reply")
            raise InterpreterUnavailable from None
        if not isinstance(content, str):
            raise InterpreterUnavailable
        return content

    async def aclose(self) -> None:
        await self._client.aclose()  # safe to call twice
