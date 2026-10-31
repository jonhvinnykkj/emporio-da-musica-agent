"""The evaluation arena, proven without network: a fake client stands in for the model."""

import json
import re
from datetime import datetime

import pytest

from emporio.agent import FALLBACK_TEXT, Turn
from emporio.tools import StoreData
from evals import burst, redteam, run
from evals.cases import CASES, HUNTER_CASES, Case
from fakes import FakeClient, MemoryJournal, anthropic_error, response, text_block


def turn(text: str, **kwargs: int) -> Turn:
    return Turn(text=text, **kwargs)


class TestFailures:
    case = Case("c", ("oi",), must_match=(r"ter[cç]a",), must_not_match=(r"segunda",))

    def test_passes_when_final_matches_and_nothing_forbidden(self):
        assert run.failures(self.case, [turn("Abrimos na TERÇA às 9h")]) == []

    def test_missing_pattern_is_reported(self):
        problems = run.failures(self.case, [turn("Abrimos amanhã")])
        assert problems == [r"missing: ter[cç]a"]

    def test_must_match_looks_only_at_the_final_answer(self):
        assert run.failures(self.case, [turn("terça"), turn("tchau")]) != []

    def test_must_not_match_looks_at_every_answer(self):
        problems = run.failures(self.case, [turn("segunda, talvez"), turn("terça")])
        assert problems == ["forbidden: segunda"]

    def test_tool_names_and_order_are_not_required(self):
        assert run.failures(Case("c", ("oi",)), [turn("qualquer coisa")]) == []


class TestCases:
    def test_there_are_twenty_with_unique_ids(self):
        assert len(CASES) == 20
        assert len({case.id for case in CASES}) == 20

    def test_clocks_match_the_scenarios(self):
        by_id = {case.id: case for case in CASES}
        assert by_id["03_closed_before_holiday"].now == datetime(2026, 10, 31, 14, 0)
        assert by_id["03_closed_before_holiday"].now.weekday() == 5
        assert by_id["02_closed_saturday_afternoon"].now.weekday() == 5

    def test_wrong_phone_case_has_three_consecutive_turns(self):
        case = next(c for c in CASES if c.id == "13_wrong_phone_three_times")
        assert len(case.turns) == 3

    def test_patterns_are_valid_regexes(self):
        for case in [*CASES, *HUNTER_CASES]:
            for pattern in (*case.must_match, *case.must_not_match):
                re.compile(pattern)


@pytest.fixture(scope="module")
def data(data_dir):
    return StoreData.load(data_dir)


ADDRESS = "Fica na Rua 14 de Maio, 3200, em Campo Grande."


class TestEvaluate:
    def test_a_case_completes_with_a_fake_client(self, data):
        case = next(c for c in CASES if c.id == "01_store_address")
        client = FakeClient(*[response(text_block(ADDRESS)) for _ in range(2)])
        spend = run.Spend(budget=1.0)
        lines: list[str] = []
        results = run.evaluate(client, data, MemoryJournal(), [case], 2, spend, lines.append)
        assert results[0].passed and results[0].passed_rounds == 2
        assert lines == ["PASS  01_store_address  2/2"]
        assert len(client.requests) == 2
        assert spend.tokens == [20, 6, 10]

    def test_a_wrong_answer_fails_the_round_and_shows_the_answer(self, data):
        case = next(c for c in CASES if c.id == "01_store_address")
        client = FakeClient(response(text_block(ADDRESS)), response(text_block("Não sei.")))
        results = run.evaluate(client, data, MemoryJournal(), [case], 2, run.Spend(1.0), lambda _: None)
        assert not results[0].passed and results[0].passed_rounds == 1
        assert any("round 2" in p and "Não sei." in p for p in results[0].problems)

    def test_each_round_starts_a_new_session(self, data):
        case = Case("c", ("oi",))
        client = FakeClient(response(text_block("a")), response(text_block("b")))
        run.evaluate(client, data, MemoryJournal(), [case], 2, run.Spend(1.0), lambda _: None)
        assert all(len(request["messages"]) == 1 for request in client.requests)

    def test_budget_stops_the_run(self, data):
        case = Case("c", ("oi",))
        big = response(text_block("a"))
        big.usage.output_tokens = 1_000_000  # US$ 0.50 on Haiku
        client = FakeClient(big, big, big)
        spend = run.Spend(budget=0.6)
        with pytest.raises(run.BudgetExceeded):
            run.evaluate(client, data, MemoryJournal(), [case], 3, spend, lambda _: None)
        assert len(client.requests) == 2

    def test_clock_comes_from_the_case(self, data):
        case = Case("c", ("oi",), now=datetime(2026, 10, 31, 14, 0))
        client = FakeClient(response(text_block("a")))
        run.evaluate(client, data, MemoryJournal(), [case], 1, run.Spend(1.0), lambda _: None)
        assert "sábado, 31/10/2026, 14:00" in json.dumps(client.requests[0]["messages"], ensure_ascii=False)


class TestCost:
    def test_haiku_prices_cache_reads_at_ten_percent(self):
        t = [turn("x", input_tokens=1_000_000, cached_tokens=1_000_000, output_tokens=1_000_000)]
        assert run.cost_usd("claude-haiku-5-5", t) == pytest.approx(0.10 + 0.01 + 0.50)

    def test_sonnet_and_opus_rates(self):
        t = [turn("x", input_tokens=1_000_000, output_tokens=1_000_000)]
        assert run.cost_usd("claude-sonnet-5-5", t) == pytest.approx(12.0)
        assert run.cost_usd("claude-opus-5-5", t) == pytest.approx(24.0)

    def test_unknown_model_is_billed_at_the_highest_rate(self):
        t = [turn("x", output_tokens=1_000_000)]
        assert run.cost_usd("claude-future", t) == pytest.approx(20.0)


class TestMain:
    def test_missing_env_exits_without_calling_the_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run, "ROOT", tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-from-the-shell")  # only the project's .env counts

        def forbidden():
            raise AssertionError("client must not be created")

        with pytest.raises(SystemExit) as stop:
            run.main(["--rounds", "1"], client_factory=forbidden)
        assert ".env" in str(stop.value)

    def test_env_without_key_exits(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
        monkeypatch.setattr(run, "ROOT", tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            run.main(["--rounds", "1"], client_factory=lambda: None)

    @pytest.fixture
    def arena(self, tmp_path, monkeypatch, data):
        """A project root with a fake key and the real store data, so main() runs end to end."""
        (tmp_path / "evals").mkdir()
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=fake-key-for-tests\n", encoding="utf-8")
        monkeypatch.setattr(run, "ROOT", tmp_path)
        monkeypatch.setattr(StoreData, "load", classmethod(lambda cls, _: data))
        return tmp_path

    def test_only_run_prints_failures_and_does_not_write_results(self, arena, capsys):
        client = FakeClient(response(text_block("Sem endereço")))
        code = run.main(["--rounds", "1", "--only", "01_store_address"], client_factory=lambda: client)
        assert code == 1
        assert "FAIL  01_store_address" in capsys.readouterr().out
        assert not (arena / "evals" / "results.md").exists()

    def test_full_run_writes_results(self, arena, monkeypatch):
        monkeypatch.setattr(run, "CASES", [Case("only", ("oi",))])
        client = FakeClient(response(text_block("oi")))
        assert run.main(["--rounds", "1"], client_factory=lambda: client) == 0
        written = (arena / "evals" / "results.md").read_text(encoding="utf-8")
        assert "1/1 cases passed" in written and "| only | 1/1 |" in written

    def test_budget_exhaustion_returns_1_and_writes_nothing(self, arena, monkeypatch, capsys):
        monkeypatch.setattr(run, "CASES", [Case("only", ("oi",))])
        big = response(text_block("oi"))
        big.usage.output_tokens = 1_000_000
        code = run.main(["--rounds", "3", "--budget", "0.1"], client_factory=lambda: FakeClient(big))
        assert code == 1
        assert "Orçamento" in capsys.readouterr().err
        assert not (arena / "evals" / "results.md").exists()


class TestRedTeam:
    def test_has_at_least_forty_messages_in_eight_groups(self):
        assert len(redteam.RED_TEAM) == 8
        assert sum(len(messages) for messages in redteam.RED_TEAM.values()) >= 40

    def test_customer_phone_and_email_are_detected_in_any_format(self, data_dir):
        phones, emails = redteam.contact_values(data_dir)
        shingles = redteam.prompt_shingles()
        assert redteam.leaks(["Ligue para 67 99654-7821"], phones, emails, shingles)
        assert redteam.leaks(["é +55 (67) 99654-7821"], phones, emails, shingles)
        assert redteam.leaks(["Escreva para ANACAROL.ferreira@coldmail.com"], phones, emails, shingles)
        store_channels = "Ligue (67) 3341-4444 ou escreva contato@emporiodamusica.com.br"
        assert not redteam.leaks([store_channels], phones, emails, shingles)

    def test_prompt_stretch_is_detected_but_short_phrases_are_not(self, data_dir):
        phones, emails = redteam.contact_values(data_dir)
        shingles = redteam.prompt_shingles()
        leaked = "Claro: Você é o Tom, assistente virtual da Empório da Música, loja de instrumentos musicais"
        assert redteam.leaks([leaked], phones, emails, shingles)
        assert not redteam.leaks(["Sou o Tom, assistente virtual da loja."], phones, emails, shingles)

    def test_unsourced_amount_in_the_final_answer_fails(self, data, data_dir):
        phones, emails = redteam.contact_values(data_dir)
        bad = redteam.check("quero desconto", turn("Fica R$ 59,99 pra você!"), data, phones, emails)
        assert any("amount without source" in p for p in bad)
        good = redteam.check("custa R$ 59,99?", turn("Você escreveu R$ 59,99."), data, phones, emails)
        assert good == []

    def test_run_with_a_clean_fake_client_passes_every_probe(self, data, data_dir):
        total = sum(len(m) for m in redteam.RED_TEAM.values())
        reply = response(text_block("Posso ajudar com instrumentos da loja."))
        client = FakeClient(*[reply] * total)
        probes = redteam.run_red_team(client, data, MemoryJournal(), run.Spend(5.0), data_dir, lambda _: None)
        assert len(probes) == total and all(not p.problems for p in probes)
        assert "passed" in redteam.summarize(probes, run.Spend(0.0))

    def test_run_flags_a_leaking_fake_client(self, data, data_dir):
        total = sum(len(m) for m in redteam.RED_TEAM.values())
        reply = response(text_block("O telefone dela é (67) 99654-7821."))
        client = FakeClient(*[reply] * total)
        probes = redteam.run_red_team(client, data, MemoryJournal(), run.Spend(5.0), data_dir, lambda _: None)
        assert all(p.problems for p in probes)


class TestBurst:
    def test_five_conversations_of_four_messages_with_separate_sessions(self, data):
        client = FakeClient(*[response(text_block("Certo.")) for _ in range(5 * 4)])
        spend = run.Spend(5.0)
        conversations = burst.run_burst(client, data, MemoryJournal(), spend)
        assert [len(c) for c in conversations] == [4] * 5
        assert len(client.requests) == 20
        summary = burst.summarize(conversations, spend, "claude-haiku-5-5")
        assert "median" in summary and "p95" in summary and "contingency text: 0/20" in summary

    def test_contingency_answers_are_counted(self, data):
        client = FakeClient(*[anthropic_error() for _ in range(20)])
        spend = run.Spend(5.0)
        conversations = burst.run_burst(client, data, MemoryJournal(), spend)
        assert all(t.text == FALLBACK_TEXT for c in conversations for t in c)
        assert "contingency text: 20/20" in burst.summarize(conversations, spend, "m")

    def test_percentile(self):
        assert burst.percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.95) == 100.0
        assert burst.percentile([5.0], 0.95) == 5.0
