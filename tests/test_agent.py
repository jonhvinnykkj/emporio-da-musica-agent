from datetime import datetime
from types import SimpleNamespace

import pytest

from emporio.agent import FALLBACK_TEXT, UNVERIFIED_AMOUNT_TEXT, Agent
from emporio.store import Store
from emporio.tools import StoreData


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, arguments, block_id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=block_id)


def response(*blocks, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


class FakeClient:
    """Replays scripted model responses and keeps a copy of each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


def make_agent(data, *responses):
    client = FakeClient(*responses)
    return Agent(client, data, Store(), clock=lambda: datetime(2026, 10, 28, 14, 0)), client


def test_answers_directly_without_tools(data):
    agent, _ = make_agent(data, response(text_block("Oi! Como posso ajudar?")))
    assert agent.reply("s", "oi").text == "Oi! Como posso ajudar?"


def test_runs_a_tool_and_feeds_the_result_back(data):
    agent, client = make_agent(
        data,
        response(tool_block("search_products", {"query": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00, ou R$ 2.089,05 no PIX.")),
    )
    turn = agent.reply("s", "quanto custa o takamine gd20?")
    assert turn.tool_calls[0].name == "search_products"
    assert not turn.guard_fired
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1" and "R$ 2.199,00" in result["content"]


def test_runs_parallel_tool_calls_in_one_message(data):
    agent, client = make_agent(
        data,
        response(
            tool_block("read_policy", {"sections": ["2"]}, "a"),
            tool_block("list_promotions", {}, "b"),
            stop_reason="tool_use",
        ),
        response(text_block("Pronto.")),
    )
    agent.reply("s", "horário e promoções?")
    assert [item["tool_use_id"] for item in client.requests[1]["messages"][-1]["content"]] == ["a", "b"]


def test_invented_price_goes_back_to_the_model_once(data):
    agent, client = make_agent(
        data,
        response(text_block("Custa R$ 1.999,00!")),
        response(tool_block("search_products", {"query": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00.")),
    )
    turn = agent.reply("s", "quanto custa o takamine gd20?")
    assert turn.guard_fired and turn.text == "Custa R$ 2.199,00."
    assert "1999" in client.requests[1]["messages"][-1]["content"]


def test_price_still_without_source_is_withheld(data):
    agent, _ = make_agent(data, response(text_block("Custa R$ 1.999,00!")), response(text_block("É R$ 1.999,00 mesmo.")))
    assert agent.reply("s", "preço?").text == UNVERIFIED_AMOUNT_TEXT


def test_price_from_a_past_turn_is_not_evidence(data):
    agent, _ = make_agent(
        data,
        response(tool_block("search_products", {"query": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00.")),
        response(text_block("Continua R$ 2.199,00.")),
        response(tool_block("search_products", {"query": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Continua R$ 2.199,00.")),
    )
    agent.reply("s", "preço?")
    turn = agent.reply("s", "e agora?")
    assert turn.guard_fired and turn.tool_calls


def test_history_is_text_only_and_scoped_to_the_session(data):
    agent, client = make_agent(
        data,
        response(tool_block("read_policy", {"sections": ["2"]}), stop_reason="tool_use"),
        response(text_block("Abrimos às 9h.")),
        response(text_block("Segunda a sexta.")),
        response(text_block("Oi!")),
    )
    agent.reply("a", "que horas abre?")
    agent.reply("a", "que dias?")
    agent.reply("b", "oi")
    assert client.requests[2]["messages"] == [
        {"role": "user", "content": "que horas abre?"},
        {"role": "assistant", "content": "Abrimos às 9h."},
        {"role": "user", "content": "que dias?"},
    ]
    assert client.requests[3]["messages"] == [{"role": "user", "content": "oi"}]


def test_system_prompt_stays_identical_within_a_turn(data):
    agent, client = make_agent(
        data,
        response(tool_block("list_promotions", {}), stop_reason="tool_use"),
        response(text_block("Sem novidades.")),
    )
    agent.reply("s", "promoções?")
    assert client.requests[0]["system"] == client.requests[1]["system"]


def test_clock_is_outside_the_cached_block(data):
    agent, client = make_agent(data, response(text_block("Oi!")))
    agent.reply("s", "oi")
    stable, clock = client.requests[0]["system"]
    assert "cache_control" in stable and "2026" not in stable["text"]
    assert "28/10/2026" in clock["text"]


def test_refusal_becomes_a_handoff(data):
    agent, _ = make_agent(data, response(stop_reason="refusal"))
    assert agent.reply("s", "oi").text == FALLBACK_TEXT


def test_endless_tool_loop_stops(data):
    responses = [response(tool_block("list_promotions", {}), stop_reason="tool_use") for _ in range(8)]
    agent, _ = make_agent(data, *responses)
    assert agent.reply("s", "oi").text == FALLBACK_TEXT


def test_tool_error_is_reported_to_the_model(data):
    agent, client = make_agent(
        data,
        response(tool_block("get_order", {"order_id": 8}), stop_reason="tool_use"),
        response(text_block("Preciso do seu telefone.")),
    )
    agent.reply("s", "pedido 8")
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True
