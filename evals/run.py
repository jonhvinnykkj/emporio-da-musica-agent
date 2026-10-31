"""Run the scenarios against the real model: uv run python -m evals.run [--only id ...]"""

import argparse
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from emporio.store import Store

from emporio.agent import Agent, Turn
from emporio.tools import StoreData
from evals.cases import CASES, Case

ROOT = Path(__file__).resolve().parents[1]


def failures(case: Case, turns: list[Turn]) -> list[str]:
    final, every_answer = turns[-1].text, "\n".join(turn.text for turn in turns)
    called = {call.name for turn in turns for call in turn.tool_calls}
    problems = [f"tool not called: {tool}" for tool in case.used_tools if tool not in called]
    problems += [f"missing: {p}" for p in case.must_match if not re.search(p, final, re.IGNORECASE)]
    problems += [f"forbidden: {p}" for p in case.must_not_match if re.search(p, every_answer, re.IGNORECASE)]
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="case ids to run")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    client, data = anthropic.Anthropic(), StoreData.load(ROOT / "data")
    cases = [case for case in CASES if not args.only or case.id in args.only]
    rows, passed, totals = [], 0, [0, 0, 0]
    for case in cases:
        agent = Agent(client, data, Store(), clock=lambda case=case: case.now)
        turns = [agent.reply(case.id, text) for text in case.turns]
        problems = failures(case, turns)
        passed += not problems
        totals[0] += sum(t.input_tokens for t in turns)
        totals[1] += sum(t.cached_tokens for t in turns)
        totals[2] += sum(t.output_tokens for t in turns)
        status = "PASS" if not problems else "FAIL"
        guard = " (guard fired)" if any(t.guard_fired for t in turns) else ""
        print(f"{status}  {case.id}{guard}")
        for problem in problems:
            print(f"      {problem}")
            print(f"      answer: {turns[-1].text[:300]!r}")
        rows.append(f"| {case.id} | {status}{guard} | {'; '.join(problems) or '-'} |")

    summary = (
        f"{passed}/{len(cases)} passed on `{agent.model}` at effort `{agent.effort}`. "
        f"Tokens: {totals[0]} input, {totals[1]} cached, {totals[2]} output."
    )
    print(f"\n{summary}")
    if not args.only:
        table = "\n".join(["| Case | Result | Detail |", "|---|---|---|", *rows])
        (ROOT / "evals" / "results.md").write_text(
            f"# Eval results\n\n{summary}\n\n{table}\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
