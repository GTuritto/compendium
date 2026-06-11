"""The chat-completion envelope (arch-chat-envelope): chat() + make_openai_client.

All tests drive a fake client object — no network, no SDK types beyond duck
shapes mirroring the OpenAI response objects.
"""

from __future__ import annotations

from types import SimpleNamespace

from compendium.model_clients import Completion, _approx_tokens, chat


def _response(content, usage):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def _usage(prompt, completion):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


class FakeBufferedClient:
    def __init__(self, response):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeStreamingClient:
    """Yields chunks; the final chunk carries usage and no choices."""

    def __init__(self, deltas, usage):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._deltas = deltas
        self._usage = usage

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        chunks = [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=d))],
                usage=None,
            )
            for d in self._deltas
        ]
        chunks.append(SimpleNamespace(choices=[], usage=self._usage))
        return iter(chunks)


def test_buffered_uses_usage_block():
    client = FakeBufferedClient(_response("an answer", _usage(120, 30)))
    c = chat(client, "m1", "sys", "user text")
    assert c == Completion("an answer", 120, 30)
    call = client.calls[0]
    assert call["model"] == "m1"
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user text"},
    ]
    assert "stream" not in call


def test_buffered_heuristic_when_usage_absent():
    client = FakeBufferedClient(_response("text", None))
    c = chat(client, "m1", "sys", "u" * 40)
    assert c.input_tokens == _approx_tokens("u" * 40)
    assert c.output_tokens == _approx_tokens("text")


def test_buffered_empty_content_becomes_empty_string():
    client = FakeBufferedClient(_response(None, _usage(5, 0)))
    assert chat(client, "m1", "s", "u").text == ""


def test_streaming_forwards_deltas_in_order_and_takes_final_usage():
    client = FakeStreamingClient(["Hel", "lo", None, "!"], _usage(7, 3))
    seen: list[str] = []
    c = chat(client, "m1", "sys", "user", on_token=seen.append)
    assert seen == ["Hel", "lo", "!"]  # empty/None deltas not forwarded
    assert c == Completion("Hello!", 7, 3)
    call = client.calls[0]
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}


def test_streaming_heuristic_when_no_usage_chunk():
    client = FakeStreamingClient(["abcd"], None)
    c = chat(client, "m1", "s", "x" * 8, on_token=lambda t: None)
    assert c.input_tokens == _approx_tokens("x" * 8)
    assert c.output_tokens == _approx_tokens("abcd")


def test_make_openai_client_construction_args(monkeypatch):
    import sys

    captured = {}

    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    from compendium.model_clients import make_openai_client

    make_openai_client("http://x/v1", "")
    assert captured == {"base_url": "http://x/v1", "api_key": "not-needed"}
    make_openai_client("http://x/v1", "sk-123")
    assert captured["api_key"] == "sk-123"
