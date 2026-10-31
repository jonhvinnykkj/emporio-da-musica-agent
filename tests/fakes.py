"""Test doubles for the model client and the journal, shared by the agent and CLI tests."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx  # the SDK 2.x transport

from emporio.agent import Agent, Session
from emporio.journal import Journal
from emporio.tools import StoreData

NOW = datetime(2026, 10, 28, 14, 0)


def text_block(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def thinking_block(text: str = "pensando", signature: str = "sig") -> Any:
    return SimpleNamespace(type="thinking", thinking=text, signature=signature)


def tool_block(name: str, arguments: dict[str, Any], block_id: str = "t1") -> Any:
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=block_id)


def response(*blocks: Any, stop_reason: str = "end_turn") -> Any:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=3)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


def anthropic_error() -> anthropic.APIError:
    return anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )


def authentication_error() -> anthropic.AuthenticationError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    failed = httpx.Response(401, request=request)
    return anthropic.AuthenticationError("invalid x-api-key", response=failed, body=None)


def has_tool_use(message: dict[str, Any]) -> bool:
    content = message["content"]
    if isinstance(content, str):
        return False
    return any(getattr(block, "type", None) == "tool_use" for block in content)


class FakeClient:
    """Replays scripted responses (or raises scripted errors) and keeps a copy of each request."""

    def __init__(self, *scripted: Any):
        self.scripted = list(scripted)
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class MemoryJournal(Journal):
    """Keeps events in memory. kinds() lists the events other than the routine per-turn log."""

    def __init__(self) -> None:
        super().__init__(None)
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def record(self, kind: str, session_id: str, payload: dict[str, Any]) -> None:
        self.events.append((kind, session_id, payload))

    def kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.events if kind != "mensagem"]


def make_agent(data: StoreData, *scripted: Any) -> tuple[Agent, FakeClient, Session]:
    client = FakeClient(*scripted)
    agent = Agent(client, data, MemoryJournal(), clock=lambda: NOW)
    return agent, client, agent.new_session()
