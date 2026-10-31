"""Run the scenarios against the real model.

uv run python -m evals.run --rounds 3 [--only id ...] [--model id] [--suite principal|cacador] [--budget 3.0]
"""

import argparse
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from emporio.agent import DEFAULT_EFFORT, DEFAULT_MODEL, REQUEST_TIMEOUT, Agent, Turn
from emporio.journal import Journal
from emporio.tools import StoreData
from evals.cases import CASES, HUNTER_CASES, Case

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET = 3.0
MISSING_ENV = (
    "Arquivo .env não encontrado ou sem ANTHROPIC_API_KEY. Crie {path} a partir de .env.example. "
    "Nada foi executado."
)
# US$ per million tokens: (input, output). Cache reads cost 10% and cache writes 125% of the input price.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
CACHE_READ_FACTOR = 0.10
CACHE_WRITE_FACTOR = 1.25
UNKNOWN_MODEL_PRICE = PRICES["claude-opus-5-5"]  # an unlisted model is billed at the highest rate


def failures(case: Case, turns: list[Turn]) -> list[str]:
    """Problems found by code: `must_match` on the final answer, `must_not_match` on every answer."""
    final, every_answer = turns[-1].text, "\n".join(turn.text for turn in turns)
    problems = [f"missing: {p}" for p in case.must_match if not re.search(p, final, re.IGNORECASE)]
    problems += [f"forbidden: {p}" for p in case.must_not_match if re.search(p, every_answer, re.IGNORECASE)]
    return problems


def cost_usd(model: str, turns: list[Turn]) -> float:
    price_in, price_out = PRICES.get(model, UNKNOWN_MODEL_PRICE)
    fresh = sum(turn.input_tokens for turn in turns)
    cached = sum(turn.cached_tokens for turn in turns)
    written = sum(turn.cache_write_tokens for turn in turns)
    output = sum(turn.output_tokens for turn in turns)
    input_cost = fresh + cached * CACHE_READ_FACTOR + written * CACHE_WRITE_FACTOR
    return (input_cost * price_in + output * price_out) / 1_000_000


def token_totals(turns: list[Turn]) -> tuple[int, int, int, int]:
    """(fresh input, cache reads, output, cache writes)"""
    return (
        sum(turn.input_tokens for turn in turns),
        sum(turn.cached_tokens for turn in turns),
        sum(turn.output_tokens for turn in turns),
        sum(turn.cache_write_tokens for turn in turns),
    )


class BudgetExceeded(Exception):
    def __init__(self, spent: float, budget: float):
        super().__init__(f"Orçamento de US$ {budget:.2f} estourado (gasto US$ {spent:.4f}). Execução parada.")


@dataclass
class Spend:
    """Running cost of one script; `charge` stops everything once the budget is crossed."""

    budget: float
    spent: float = 0.0
    tokens: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    def charge(self, model: str, turns: list[Turn]) -> None:
        self.spent += cost_usd(model, turns)
        for index, amount in enumerate(token_totals(turns)):
            self.tokens[index] += amount
        if self.spent > self.budget:
            raise BudgetExceeded(self.spent, self.budget)


@dataclass
class CaseResult:
    case: Case
    passed_rounds: int
    rounds: int
    problems: list[str]
    guard_fired: bool

    @property
    def passed(self) -> bool:
        return self.passed_rounds == self.rounds


def journal_for(name: str) -> Journal:
    return Journal(ROOT / ".emporio" / f"{name}.jsonl")


def write_results(name: str, section: str, partial: bool = False) -> Path:
    """Write evals/results/<name>.md. Each suite owns its file, so one run never erases another."""
    path = ROOT / "evals" / "results" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    note = "> PARTIAL: budget stop; only what is listed completed.\n\n" if partial else ""
    path.write_text(f"# Eval results: {name}\n\n{note}{section.strip()}\n", encoding="utf-8")
    return path


def evaluate(
    client: Any,
    data: StoreData,
    journal: Journal,
    cases: list[Case],
    rounds: int,
    spend: Spend,
    write: Callable[[str], None] = print,
    results: list[CaseResult] | None = None,
) -> list[CaseResult]:
    """Each round of each case gets a fresh agent and session. Raises BudgetExceeded when the cap is hit;
    pass `results` to keep the cases finished before that."""
    results = [] if results is None else results
    for case in cases:
        passed_rounds, problems, guard = 0, [], False
        for round_number in range(1, rounds + 1):
            agent = Agent(client, data, journal, clock=lambda case=case: case.now)
            session = agent.new_session()
            turns: list[Turn] = []
            try:
                for text in case.turns:
                    turns.append(agent.reply(session, text))
            finally:
                spend.charge(agent.model, turns)
            found = failures(case, turns)
            passed_rounds += not found
            guard = guard or any(turn.guard_fired for turn in turns)
            answer = turns[-1].text[:200]
            problems += [f"round {round_number}: {problem} | answer: {answer!r}" for problem in found]
        result = CaseResult(case, passed_rounds, rounds, problems, guard)
        results.append(result)
        write(f"{'PASS' if result.passed else 'FAIL'}  {case.id}  {passed_rounds}/{rounds}")
        for problem in problems:
            write(f"      {problem}")
    return results


def headline(results: list[CaseResult], spend: Spend, model: str, effort: str) -> str:
    perfect = sum(result.passed for result in results)
    fresh, cached, output, written = spend.tokens
    return (
        f"{perfect}/{len(results)} cases passed every round on `{model}` at effort `{effort}`. "
        f"Tokens: {fresh} input, {cached} cache read, {written} cache write, {output} output. "
        f"Estimated cost: US$ {spend.spent:.4f}."
    )


def summarize(results: list[CaseResult], spend: Spend, model: str, effort: str, suite: str) -> str:
    rows = [
        f"| {r.case.id} | {r.passed_rounds}/{r.rounds}{' (guard fired)' if r.guard_fired else ''} "
        f"| {'; '.join(r.problems) or '-'} |"
        for r in results
    ]
    return (
        f"## Suite `{suite}`\n\n{headline(results, spend, model, effort)}\n\n"
        + "\n".join(["| Case | Rounds passed | Detail |", "|---|---|---|", *rows])
    )


def require_key(root: Path) -> None:
    """Load the project's own .env (it wins over the environment) or stop before any call."""
    if not (root / ".env").exists():
        raise SystemExit(MISSING_ENV.format(path=root / ".env"))
    load_dotenv(root / ".env", override=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(MISSING_ENV.format(path=root / ".env"))


def make_client() -> Any:
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT)


def main(argv: list[str] | None = None, client_factory: Callable[[], Any] = make_client) -> int:
    parser = argparse.ArgumentParser(description="Scenarios against the real model")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--only", nargs="*", help="case ids to run")
    parser.add_argument("--model", help="model id (default: EMPORIO_MODEL or the agent default)")
    parser.add_argument("--suite", choices=("principal", "cacador"), default="principal")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="US$ cap for this run")
    args = parser.parse_args(argv)

    require_key(ROOT)
    if args.model:
        os.environ["EMPORIO_MODEL"] = args.model
    suite = CASES if args.suite == "principal" else HUNTER_CASES
    cases = [case for case in suite if not args.only or case.id in args.only]
    if not cases:
        raise SystemExit("Nenhum cenário selecionado (a suíte 'cacador' depende de evals/hunter_cases.py).")

    data = StoreData.load(ROOT / "data")
    spend = Spend(args.budget)
    results: list[CaseResult] = []
    model = os.environ.get("EMPORIO_MODEL", DEFAULT_MODEL)
    effort = os.environ.get("EMPORIO_EFFORT", DEFAULT_EFFORT)
    try:
        evaluate(client_factory(), data, journal_for("evals"), cases, args.rounds, spend, results=results)
    except BudgetExceeded as stop:
        print(stop, file=sys.stderr)
        if results and not args.only:
            write_results(args.suite, summarize(results, spend, model, effort, args.suite), partial=True)
        return 1
    except anthropic.AuthenticationError:
        print("Chave inválida: confira ANTHROPIC_API_KEY no .env.", file=sys.stderr)
        return 1

    summary = summarize(results, spend, model, effort, args.suite)
    print(f"\n{headline(results, spend, model, effort)}")
    if not args.only:
        write_results(args.suite, summary)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
