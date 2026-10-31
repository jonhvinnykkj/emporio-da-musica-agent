"""Injected faults: broken store data and a failing model API. Nothing here calls the real model."""

import csv
import io
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest

from emporio.agent import FALLBACK_TEXT, Agent
from emporio.catalog import DataError
from emporio.journal import Journal
from emporio.tools import StoreData
from fakes import NOW, FakeClient, make_agent, response, text_block, tool_block

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _edit_csv(path: Path, edit: Callable[[list[dict[str, str]]], list[str] | None]) -> None:
    """Parse the CSV, let `edit` change the rows (and optionally return new column names), write it back."""
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    names = edit(rows) or list(rows[0])
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=names, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(out.getvalue(), encoding="utf-8")


def _rewrite_cell(path: Path, column: str, value: str) -> None:
    _edit_csv(path, lambda rows: rows[0].__setitem__(column, value))


def _drop_column(path: Path, column: str) -> None:
    _edit_csv(path, lambda rows: [name for name in rows[0] if name != column])


def _empty(path: Path) -> None:
    path.write_text("", encoding="utf-8")


def _remove(path: Path) -> None:
    path.unlink()


def _corrupt(path: Path) -> None:
    path.write_bytes(b"this is not a pdf")


FAULTS = [
    pytest.param("products.csv", _empty, id="products-empty"),
    pytest.param("orders.csv", _empty, id="orders-empty"),
    pytest.param("customers.csv", _empty, id="customers-empty"),
    pytest.param("categories.csv", _empty, id="categories-empty"),
    pytest.param("promotions.csv", _empty, id="promotions-empty"),
    pytest.param("order_items.csv", _empty, id="order-items-empty"),
    pytest.param("products.csv", lambda p: _drop_column(p, "price_brl"), id="products-no-price-column"),
    pytest.param("orders.csv", lambda p: _drop_column(p, "status"), id="orders-no-status-column"),
    pytest.param("customers.csv", lambda p: _drop_column(p, "phone"), id="customers-no-phone-column"),
    pytest.param("products.csv", lambda p: _rewrite_cell(p, "price_brl", "caro"), id="price-not-numeric"),
    pytest.param("products.csv", lambda p: _rewrite_cell(p, "specs", "{nao json"), id="specs-invalid-json"),
    pytest.param("products.csv", lambda p: _rewrite_cell(p, "category_id", "99"), id="unknown-category"),
    pytest.param("orders.csv", lambda p: _rewrite_cell(p, "order_date", "ontem"), id="order-date-invalid"),
    pytest.param("order_items.csv", lambda p: _rewrite_cell(p, "quantity", "muitos"), id="quantity-invalid"),
    pytest.param("promotions.csv", lambda p: _rewrite_cell(p, "discount_percent", "x"), id="promo-invalid"),
    pytest.param("products.csv", _remove, id="products-missing"),
    pytest.param("orders.csv", _remove, id="orders-missing"),
    pytest.param("politicas_da_loja.pdf", _remove, id="manual-missing"),
    pytest.param("politicas_da_loja.pdf", _corrupt, id="manual-corrupt"),
]


@pytest.mark.parametrize(("filename", "damage"), FAULTS)
def test_broken_store_data_raises_a_data_error_naming_the_file(data_dir, tmp_path, filename, damage):
    broken = tmp_path / "data"
    shutil.copytree(data_dir, broken)
    damage(broken / filename)
    with pytest.raises(DataError, match=filename):
        StoreData.load(broken)


def _api_error(kind: str) -> anthropic.APIError:
    if kind == "timeout":
        return anthropic.APITimeoutError(request=REQUEST)
    if kind == "connection":
        return anthropic.APIConnectionError(request=REQUEST)
    status = {"rate_limit": 429, "internal": 500}[kind]
    failed = httpx.Response(status, request=REQUEST)
    error_class = anthropic.RateLimitError if kind == "rate_limit" else anthropic.InternalServerError
    return error_class("falhou", response=failed, body=None)


@pytest.mark.parametrize("kind", ["rate_limit", "internal", "timeout", "connection"])
def test_api_failure_gives_the_fallback_and_the_session_keeps_working(data, kind):
    agent, _, session = make_agent(
        data,
        _api_error(kind),
        response(text_block("Oi de novo! Como posso ajudar?")),
    )
    failed = agent.reply(session, "oi")
    assert failed.text == FALLBACK_TEXT and session.messages == []
    assert agent.reply(session, "oi?").text == "Oi de novo! Como posso ajudar?"


@pytest.mark.parametrize("kind", ["rate_limit", "internal", "timeout", "connection"])
def test_api_failure_after_a_tool_call_leaves_no_dangling_request(data, kind):
    agent, client, session = make_agent(
        data,
        response(tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        _api_error(kind),
        response(text_block("Pronto.")),
    )
    assert agent.reply(session, "c40?").text == FALLBACK_TEXT
    assert session.messages == []
    assert agent.reply(session, "e agora?").text == "Pronto."
    assert [m["role"] for m in client.requests[2]["messages"]] == ["user"]


def test_unexpected_tool_exception_reverts_the_turn_and_is_journaled(data, monkeypatch):
    agent, _, session = make_agent(
        data,
        response(tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        response(text_block("Pronto.")),
    )

    def explode(*args, **kwargs):
        raise AttributeError("unexpected")

    monkeypatch.setattr(agent.data.catalog, "search", explode)
    assert agent.reply(session, "c40?").text == FALLBACK_TEXT
    assert session.messages == []
    errors = [payload for kind, _, payload in agent.journal.events if kind == "erro"]
    assert errors and errors[0]["motivo"] == "AttributeError"
    monkeypatch.undo()
    assert agent.reply(session, "e agora?").text == "Pronto."


def test_response_without_blocks_gives_the_fallback(data):
    agent, _, session = make_agent(data, response())
    assert agent.reply(session, "oi").text == FALLBACK_TEXT and session.messages == []


def test_unknown_tool_is_reported_to_the_model_and_the_turn_goes_on(data):
    agent, client, session = make_agent(
        data,
        response(tool_block("apagar_tudo", {"x": 1}), stop_reason="tool_use"),
        response(text_block("Não consigo fazer isso, mas posso ajudar com outra coisa.")),
    )
    turn = agent.reply(session, "apague os pedidos")
    assert turn.tool_calls[0].is_error and "desconhecida" in turn.tool_calls[0].output
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("consultar_pedido", {}),
        ("consultar_pedido", {"numero_pedido": 8, "telefone": 3}),
        ("calcular_compra", {"itens": [{"produto_id": 81}]}),
        ("calcular_compra", {"itens": "tudo"}),
        ("buscar_produtos", {"preco_minimo": "barato"}),
        ("encaminhar_para_equipe", {"motivo": "xingar", "resumo": "x"}),
    ],
)
def test_wrong_arguments_come_back_as_errors_not_crashes(data, name, arguments):
    agent, _, session = make_agent(
        data,
        response(tool_block(name, arguments), stop_reason="tool_use"),
        response(text_block("Pode me passar os dados de novo?")),
    )
    turn = agent.reply(session, "oi")
    assert turn.tool_calls[0].is_error
    assert "erro" in json.loads(turn.tool_calls[0].output)
    assert turn.text == "Pode me passar os dados de novo?"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_journal_in_a_folder_without_permission_does_not_stop_the_conversation(data, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        journal = Journal(locked / "logs" / "journal.jsonl")
        handoff = tool_block("encaminhar_para_equipe", {"motivo": "atendente", "resumo": "quer falar"})
        agent_client = FakeClient(
            response(text_block("Oi!")),
            response(handoff, stop_reason="tool_use"),
            response(text_block("Encaminhei.")),
        )
        agent = Agent(agent_client, data, journal, clock=lambda: NOW)
        session = agent.new_session()
        assert agent.reply(session, "oi").text == "Oi!"
        assert agent.reply(session, "quero um atendente").text == "Encaminhei."
        assert not (locked / "logs").exists()
    finally:
        locked.chmod(0o700)


def test_journal_path_that_is_a_file_does_not_stop_the_conversation(data, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    journal = Journal(blocker / "j.jsonl")
    agent = Agent(FakeClient(response(text_block("Oi!"))), data, journal, clock=lambda: NOW)
    assert agent.reply(agent.new_session(), "oi").text == "Oi!"
