"""The example recorder, proven with a fake client: no key, no network."""

import shutil
from pathlib import Path

import pytest

from fakes import FakeClient, response, text_block
from scripts import record_examples as rec


@pytest.fixture
def root(tmp_path, monkeypatch):
    shutil.copytree(Path(__file__).resolve().parents[1] / "data", tmp_path / "data")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=fake-key-for-tests\n", encoding="utf-8")
    return tmp_path


def turns_needed() -> int:
    return sum(len(rec.find_case(case_id).turns) for _, case_id, _ in rec.EXAMPLES)


def test_five_examples_come_from_the_scenarios_5_4_12_16_20():
    assert [case_id[:2] for _, case_id, _ in rec.EXAMPLES] == ["05", "04", "12", "16", "20"]


def test_without_env_it_stops_with_a_clear_message_and_calls_nothing(tmp_path):
    def forbidden():
        raise AssertionError("client must not be created")

    with pytest.raises(SystemExit) as stop:
        rec.main(client_factory=forbidden, root=tmp_path)
    assert ".env" in str(stop.value) and not (tmp_path / "examples").exists()


def test_env_without_a_key_stops(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        rec.main(client_factory=lambda: None, root=tmp_path)


def test_records_one_file_per_example_with_clock_and_answers(root, capsys):
    client = FakeClient(*[response(text_block("Resposta gravada.")) for _ in range(turns_needed())])
    assert rec.main(client_factory=lambda: client, root=root) == 0
    files = sorted((root / "examples").glob("*.md"))
    assert len(files) == 5
    text = (root / "examples" / "01-violoes-ate-1000.md").read_text(encoding="utf-8")
    assert "**Cliente:** Quais opções de violões" in text and "**Tom:** Resposta gravada." in text
    assert "Wednesday 2026-10-28 14:00" in text
    assert "wrote examples/01-violoes-ate-1000.md" in capsys.readouterr().out


def test_tools_used_are_listed(root):
    from fakes import tool_block

    scripted = [
        response(tool_block("buscar_produtos", {"categoria": "violao"}), stop_reason="tool_use"),
        response(text_block("Achei.")),
    ]
    scripted += [response(text_block("ok")) for _ in range(turns_needed() - 1)]
    rec.main(client_factory=lambda: FakeClient(*scripted), root=root)
    text = (root / "examples" / "01-violoes-ate-1000.md").read_text(encoding="utf-8")
    assert '> `buscar_produtos({"categoria": "violao"})`' in text


def test_a_rejected_key_returns_1(root, capsys):
    from fakes import authentication_error

    assert rec.main(client_factory=lambda: FakeClient(authentication_error()), root=root) == 1
    assert "Chave inválida" in capsys.readouterr().err
