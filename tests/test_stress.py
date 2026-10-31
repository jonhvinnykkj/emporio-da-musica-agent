"""Load with a stateless fake model and the real tools. Time limits are loose on purpose: they catch
accidental quadratic work, not a slow laptop."""

import json
import threading
import time
from typing import Any

from emporio.agent import Agent
from emporio.journal import Journal
from fakes import NOW, MemoryJournal, anthropic_error, has_tool_use, response, text_block, tool_block

TURN_BUDGET_SECONDS = 20
LOCKED_MESSAGE = "Muitas tentativas"


class ScriptedByCustomer:
    """Decides each reply from the conversation itself, so many threads can share one client.

    A customer message starting with 'pedido' asks for an order check with a wrong phone; anything else
    runs a catalog search. After a tool result the model answers in plain text.
    """

    def __init__(self) -> None:
        self.messages = self
        self.calls = 0
        self._lock = threading.Lock()

    def create(self, **kwargs: Any) -> Any:
        with self._lock:
            self.calls += 1
        last = kwargs["messages"][-1]
        if (
            last["role"] == "user"
            and isinstance(last["content"], list)
            and last["content"][0]["type"] == "tool_result"
        ):
            return response(text_block(_tool_summary(last["content"][0]["content"])))
        customer_text = last["content"][1]["text"]
        if customer_text.startswith("falha"):
            raise anthropic_error()
        if customer_text.startswith("pedido"):
            arguments = {"numero_pedido": 8, "telefone": "(67) 90000-0000"}
            return response(tool_block("consultar_pedido", arguments, "o1"), stop_reason="tool_use")
        return response(tool_block("buscar_produtos", {"consulta": "violao"}, "b1"), stop_reason="tool_use")


def _tool_summary(output: str) -> str:
    result = json.loads(output)
    if result.get("bloqueado"):
        return LOCKED_MESSAGE
    if "total_encontrado" in result:
        return f"Encontrei {result['total_encontrado']} opções."
    return "Não achei esse pedido."


def _agent(data, journal=None) -> Agent:
    return Agent(ScriptedByCustomer(), data, journal or MemoryJournal(), clock=lambda: NOW)


def test_a_thousand_turns_stay_fast(data):
    agent = _agent(data)
    started = time.perf_counter()
    session = agent.new_session()
    for index in range(1000):
        if index % 100 == 0:
            session = agent.new_session()
        turn = agent.reply(session, "tem violão?")
        assert turn.text.startswith("Encontrei") and turn.tool_calls[0].name == "buscar_produtos"
    assert time.perf_counter() - started < TURN_BUDGET_SECONDS


def test_fifty_threads_do_not_mix_sessions(data, tmp_path):
    path = tmp_path / "journal.jsonl"
    agent = _agent(data, Journal(path))
    outcomes: dict[int, list[str]] = {}
    failures: list[BaseException] = []

    def talk(worker: int) -> None:
        try:
            session = agent.new_session()
            checks_order = worker % 2 == 0
            outcomes[worker] = [
                agent.reply(
                    session, f"pedido {worker} {turn}" if checks_order else f"violao {worker} {turn}"
                ).text
                for turn in range(20)
            ]
        except BaseException as error:  # noqa: BLE001 - reported in the main thread
            failures.append(error)

    threads = [threading.Thread(target=talk, args=(worker,)) for worker in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    for worker, texts in outcomes.items():
        if worker % 2 == 0:
            assert texts[:3] == ["Não achei esse pedido."] * 3 and set(texts[3:]) == {LOCKED_MESSAGE}
        else:
            assert all(text.startswith("Encontrei") for text in texts)

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    per_session: dict[str, int] = {}
    for event in events:
        if event["kind"] == "mensagem":
            per_session[event["session_id"]] = per_session.get(event["session_id"], 0) + 1
    assert len(per_session) == 50 and set(per_session.values()) == {20}


def test_two_hundred_turn_conversation_stays_valid(data):
    agent = _agent(data)
    session = agent.new_session()
    for index in range(200):
        failing = index % 17 == 16
        before, snapshot = len(session.messages), list(session.messages)
        agent.reply(session, "falha na API" if failing else "violão barato")
        assert session.messages[:before] == snapshot  # history only changes at the end
        assert (len(session.messages) == before) == failing  # a failed turn is rolled back whole
        assert not has_tool_use(session.messages[-1]) if session.messages else True
    messages = session.messages
    assert messages[-1]["role"] == "assistant"
    assert [m["role"] for m in messages[:4]] == ["user", "assistant", "user", "assistant"]
    pending: set[str] = set()
    for message in messages:
        if isinstance(message["content"], str):
            continue
        for block in message["content"]:
            if getattr(block, "type", None) == "tool_use":
                pending.add(block.id)
            elif isinstance(block, dict) and block.get("type") == "tool_result":
                pending.discard(block["tool_use_id"])
    assert not pending
