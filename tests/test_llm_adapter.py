"""The Groq adapter against a fake HTTP transport: no network, no real key."""

import asyncio
import json
import logging

import httpx
import pytest

from leregister.adapters.llm import GroqInterpreter
from leregister.core.ports import InterpreterUnavailable

KEY = "gsk_test_secret_key"


def make(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqInterpreter(KEY, kwargs.pop("model", "some-model"), client=client, **kwargs)


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def run(coro):
    return asyncio.run(coro)


def test_a_good_call_returns_the_model_text_and_sends_the_expected_request():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok('{"command": "none"}')

    interpreter = make(handler, model="llama-3.3-70b-versatile")
    assert run(interpreter.complete("SYSTEM", "USER")) == '{"command": "none"}'
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    assert body["model"] == "llama-3.3-70b-versatile"
    assert body["messages"] == [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "USER"}]
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0
    assert body["max_tokens"] <= 2000
    assert set(body) == {"model", "messages", "temperature", "max_tokens", "response_format"}  # no tools


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_http_errors_including_rate_limit_mean_unavailable(status):
    interpreter = make(lambda request: httpx.Response(status, json={"error": "nope"}))
    with pytest.raises(InterpreterUnavailable):
        run(interpreter.complete("s", "u"))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": 5}}]}),
    ],
)
def test_an_unreadable_reply_means_unavailable(response):
    interpreter = make(lambda request: response)
    with pytest.raises(InterpreterUnavailable):
        run(interpreter.complete("s", "u"))


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), httpx.ConnectError("c")])
def test_timeouts_and_network_errors_mean_unavailable(error):
    def handler(request):
        raise error

    with pytest.raises(InterpreterUnavailable):
        run(make(handler).complete("s", "u"))


def test_the_key_and_the_message_never_reach_the_logs_or_the_repr(caplog):
    interpreter = make(lambda request: httpx.Response(429, json={"error": "slow down", "echo": "SECRET TEXT"}))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InterpreterUnavailable):
            run(interpreter.complete("system words", "SECRET TEXT"))
    assert KEY not in caplog.text and "SECRET TEXT" not in caplog.text and "slow down" not in caplog.text
    assert KEY not in repr(interpreter) and KEY not in str(interpreter)


def test_the_configured_timeout_is_passed_to_the_request():
    seen = {}

    def handler(request):
        seen["timeout"] = request.extensions["timeout"]
        return ok("{}")

    run(make(handler, timeout=3.5).complete("s", "u"))
    assert seen["timeout"]["read"] == 3.5 and seen["timeout"]["connect"] == 3.5


def test_aclose_is_safe_to_call_twice():
    interpreter = make(lambda request: ok("{}"))
    run(interpreter.aclose())
    run(interpreter.aclose())


def test_a_slow_provider_is_cut_off_after_the_timeout_in_total():
    async def slow(request):
        await asyncio.sleep(1)
        return ok("{}")

    interpreter = make(slow, timeout=0.05)
    with pytest.raises(InterpreterUnavailable):
        run(interpreter.complete("s", "u"))


def test_one_client_is_shared_between_concurrent_calls():
    interpreter = make(lambda request: ok("{}"))
    client = interpreter._client

    async def both():
        await asyncio.gather(interpreter.complete("s", "u"), interpreter.complete("s", "u"))

    run(both())
    assert interpreter._client is client


def test_a_reasoning_model_gets_a_low_reasoning_effort_and_other_models_do_not():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return ok("{}")

    run(make(handler, model="openai/gpt-oss-20b").complete("s", "u"))
    run(make(handler, model="llama-3.3-70b-versatile").complete("s", "u"))
    assert bodies[0]["reasoning_effort"] == "low" and "reasoning_effort" not in bodies[1]
