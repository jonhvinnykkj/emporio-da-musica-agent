import anthropic
import pytest

from emporio import cli
from emporio.agent import Agent
from emporio.tools import StoreData
from fakes import NOW, FakeClient, MemoryJournal, authentication_error, response, text_block, tool_block


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


@pytest.fixture
def no_dotenv(monkeypatch):
    """Keep tests away from any real .env file and key."""
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def chat(data, scripted, lines, debug=False):
    agent = Agent(FakeClient(*scripted), data, MemoryJournal(), clock=lambda: NOW)
    feed = iter(lines)
    output: list[str] = []
    cli.run_chat(agent, debug, read=lambda prompt: next(feed), write=output.append)
    return "\n".join(output)


def test_loads_the_key_only_from_the_project_env_file(monkeypatch, no_dotenv):
    calls = []
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(SystemExit):
        cli.main([])
    assert calls == [((cli.ROOT / ".env",), {"override": True})]


def test_missing_key_exits_with_a_friendly_message(no_dotenv):
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert str(exit_info.value) == cli.MISSING_KEY


def test_data_error_exits_naming_the_file(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert "categories.csv" in str(exit_info.value)


def test_main_starts_a_chat_and_reports_the_inconsistency_count(monkeypatch, no_dotenv, capsys, data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "make_client", lambda: FakeClient(response(text_block("Oi!"))))
    monkeypatch.setattr(cli, "JOURNAL_PATH", None)
    lines = iter(["oi", "/sair"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    cli.main([])
    out = capsys.readouterr().out
    assert "inconsistências" in out and "Tom: Oi!" in out
    assert "produto" not in out


def test_debug_lists_inconsistencies_and_shows_the_trace(monkeypatch, no_dotenv, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    scripted = [
        response(tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        response(text_block("Custa R$ 1,00")),
        response(text_block("Custa R$ 1,00")),
    ]
    monkeypatch.setattr(cli, "make_client", lambda: FakeClient(*scripted))
    monkeypatch.setattr(cli, "JOURNAL_PATH", None)
    lines = iter(["preço do c40?", "/sair"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    cli.main(["--debug"])
    out = capsys.readouterr().out
    assert "produto " in out
    assert "[ferramenta] buscar_produtos" in out and "[trava]" in out and "[tokens]" in out


def test_chat_prints_the_answer_and_ignores_blank_lines(data):
    out = chat(data, [response(text_block("Oi!"))], ["", "  ", "oi", "sair"])
    assert "Tom: Oi!" in out and "[ferramenta]" not in out


def test_chat_ends_on_end_of_input(data):
    def read(prompt):
        raise EOFError

    cli.run_chat(Agent(FakeClient(), data, MemoryJournal()), False, read=read, write=lambda text: None)


def test_authentication_error_ends_the_chat_with_the_key_message(data):
    with pytest.raises(SystemExit) as exit_info:
        chat(data, [authentication_error()], ["oi"])
    assert str(exit_info.value) == cli.MISSING_KEY
    assert isinstance(authentication_error(), anthropic.APIError)
