import json

import pytest

from emporio.agent import FALLBACK_TEXT, SAFE_TEXT
from emporio.tools import StoreData
from fakes import (
    anthropic_error,
    authentication_error,
    has_tool_use,
    make_agent,
    response,
    text_block,
    thinking_block,
    tool_block,
)


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


def test_answers_directly_without_tools(data):
    agent, _, session = make_agent(data, response(text_block("Oi! Como posso ajudar?")))
    turn = agent.reply(session, "oi")
    assert turn.text == "Oi! Como posso ajudar?" and not turn.tool_calls and not turn.guard_fired


def test_runs_a_tool_and_feeds_the_result_back(data):
    agent, client, session = make_agent(
        data,
        response(tool_block("buscar_produtos", {"consulta": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00, ou R$ 2.089,05 no PIX.")),
    )
    turn = agent.reply(session, "quanto custa o takamine gd20?")
    assert turn.tool_calls[0].name == "buscar_produtos" and not turn.guard_fired
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1"
    assert "R$ 2.199,00" in result["content"]


def test_runs_parallel_tool_calls_in_one_message(data):
    agent, client, session = make_agent(
        data,
        response(
            tool_block("buscar_produtos", {"consulta": "c40"}, "a"),
            tool_block("buscar_produtos", {"consulta": "gd20"}, "b"),
            stop_reason="tool_use",
        ),
        response(text_block("Pronto.")),
    )
    agent.reply(session, "c40 e gd20?")
    assert [item["tool_use_id"] for item in client.requests[1]["messages"][-1]["content"]] == ["a", "b"]


def test_tool_error_is_reported_to_the_model(data):
    agent, client, session = make_agent(
        data,
        response(tool_block("inexistente", {}), stop_reason="tool_use"),
        response(text_block("Não consegui.")),
    )
    agent.reply(session, "oi")
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_invented_price_goes_back_to_the_model_once(data):
    agent, client, session = make_agent(
        data,
        response(text_block("Custa R$ 1.999,00!")),
        response(tool_block("buscar_produtos", {"consulta": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00.")),
    )
    turn = agent.reply(session, "quanto custa o takamine gd20?")
    assert turn.guard_fired and turn.text == "Custa R$ 2.199,00."
    correction = client.requests[1]["messages"][-1]["content"]
    assert "1999" in json.dumps(correction)


def test_price_from_a_past_turn_is_not_evidence(data):
    agent, _, session = make_agent(
        data,
        response(tool_block("buscar_produtos", {"consulta": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 2.199,00.")),
        response(text_block("Continua R$ 2.199,00.")),
        response(tool_block("buscar_produtos", {"consulta": "takamine gd20"}), stop_reason="tool_use"),
        response(text_block("Continua R$ 2.199,00.")),
    )
    agent.reply(session, "preço?")
    turn = agent.reply(session, "e agora?")
    assert turn.guard_fired and turn.tool_calls


def test_second_guard_failure_sends_safe_text_and_forwards(data):
    agent, _, session = make_agent(data, response(text_block("R$ 1,00")), response(text_block("R$ 1,00")))
    assert agent.reply(session, "preço?").text == SAFE_TEXT
    assert agent.journal.kinds() == ["encaminhamento"]
    assert [m["role"] for m in session.messages] == ["user", "assistant"]
    assert session.messages[-1]["content"] == SAFE_TEXT


def test_manual_amounts_count_as_evidence(data):
    agent, _, session = make_agent(data, response(text_block("Frete grátis acima de R$ 500,00.")))
    assert not agent.reply(session, "frete?").guard_fired


def test_customer_amounts_count_as_evidence(data):
    agent, _, session = make_agent(data, response(text_block("Entendi, seu limite é R$ 777,00.")))
    assert not agent.reply(session, "tenho R$ 777,00").guard_fired


def test_api_failure_mid_turn_keeps_the_conversation_usable(data):
    agent, _, session = make_agent(
        data,
        response(tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        anthropic_error(),
        response(text_block("Oi de novo!")),
    )
    assert "(67) 3341-4444" in agent.reply(session, "preço do c40?").text
    assert session.messages == []
    assert agent.reply(session, "oi").text == "Oi de novo!"
    assert all(not has_tool_use(m) for m in session.messages)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_unusable_stop_reasons_roll_back_to_the_fallback(data, stop_reason):
    agent, _, session = make_agent(data, response(text_block("parcial"), stop_reason=stop_reason))
    assert agent.reply(session, "oi").text == FALLBACK_TEXT
    assert session.messages == []
    assert "erro" in agent.journal.kinds()


def test_authentication_error_is_not_hidden(data):
    agent, _, session = make_agent(data, authentication_error())
    with pytest.raises(type(authentication_error())):
        agent.reply(session, "oi")
    assert session.messages == []


def test_system_stays_identical_across_turns(data):
    agent, client, session = make_agent(data, response(text_block("a")), response(text_block("b")))
    agent.reply(session, "um")
    agent.reply(session, "dois")
    assert client.requests[0]["system"] == client.requests[1]["system"]
    assert "cache_control" in client.requests[0]["system"][0]


def test_clock_opens_each_customer_turn(data):
    agent, client, session = make_agent(data, response(text_block("a")))
    agent.reply(session, "oi")
    clock, customer = client.requests[0]["messages"][-1]["content"]
    assert "28/10/2026" in clock["text"] and customer["text"] == "oi"


def test_thinking_blocks_and_earlier_messages_are_resent_untouched(data):
    thinking = thinking_block()
    agent, client, session = make_agent(
        data,
        response(thinking, tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        response(text_block("Achei.")),
        response(text_block("De nada.")),
    )
    agent.reply(session, "c40?")
    assistant = client.requests[1]["messages"][1]["content"]
    assert assistant[0] is thinking
    agent.reply(session, "obrigado")
    first_turn = client.requests[1]["messages"] + [{"role": "assistant", "content": [text_block("x")]}]
    assert client.requests[2]["messages"][:3] == first_turn[:3]
    assert client.requests[2]["messages"][1]["content"][0] is thinking


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "Não recebi sua mensagem. Pode escrever de novo?"),
        ("   ", "Não recebi sua mensagem. Pode escrever de novo?"),
        ("x" * 2001, "Sua mensagem ficou muito longa. Pode resumir em até 2000 caracteres?"),
    ],
)
def test_invalid_input_never_reaches_the_model(data, text, expected):
    agent, client, session = make_agent(data)
    assert agent.reply(session, text).text == expected
    assert client.requests == [] and session.messages == []


def test_a_message_of_exactly_2000_characters_is_accepted(data):
    agent, client, session = make_agent(data, response(text_block("ok")))
    assert agent.reply(session, "x" * 2000).text == "ok"


def test_sixth_tool_call_is_not_executed(data):
    scripted = [response(tool_block("buscar_produtos", {}), stop_reason="tool_use") for _ in range(6)]
    agent, _, session = make_agent(data, *scripted)
    turn = agent.reply(session, "oi")
    assert len(turn.tool_calls) == 5 and turn.text == FALLBACK_TEXT
    assert session.messages == []


def test_each_turn_is_logged_with_tokens_and_time(data):
    agent, _, session = make_agent(data, response(text_block("Oi!")))
    turn = agent.reply(session, "oi")
    kind, session_id, payload = agent.journal.events[-1]
    assert (kind, session_id) == ("mensagem", session.id)
    assert payload["cliente"] == "oi" and payload["resposta"] == "Oi!"
    assert (turn.input_tokens, turn.cached_tokens, turn.output_tokens) == (10, 3, 5)
    assert payload["tokens_entrada"] == 10 and payload["segundos"] == turn.seconds >= 0


def test_sessions_do_not_share_history_or_failed_lookups(data):
    agent, _, first = make_agent(data, response(text_block("a")), response(text_block("b")))
    second = agent.new_session()
    agent.reply(first, "um")
    agent.reply(second, "dois")
    assert len(first.messages) == len(second.messages) == 2
    assert first.id != second.id and first.toolbox is not second.toolbox
