"""Five simultaneous conversations of four messages each. uv run python -m evals.burst [--budget 1.0]"""

import argparse
import os
import statistics
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anthropic

from emporio.agent import DEFAULT_MODEL, FALLBACK_TEXT, Agent, Turn
from emporio.tools import StoreData
from evals.run import (
    DEFAULT_BUDGET,
    ROOT,
    BudgetExceeded,
    Spend,
    journal_for,
    make_client,
    require_key,
    write_results,
)

CONVERSATIONS = [
    [
        "Oi! Quais violões vocês têm até R$ 1000?",
        "E o Yamaha C40, quanto fica no PIX?",
        "Dá pra parcelar em quantas vezes?",
        "Vocês estão abertos amanhã?",
    ],
    [
        "Boa tarde, qual o endereço da loja?",
        "Quanto custa o Taylor 110e?",
        "E se eu pagar no PIX?",
        "Obrigado!",
    ],
    [
        "Cadê meu pedido? Número 8, telefone (67) 99654-7821",
        "Pode abrir um chamado para isso?",
        "Qual o telefone da loja?",
        "Valeu.",
    ],
    [
        "Vocês têm ukulele concert?",
        "Quanto fica 2 Ohana CK-20 com entrega em Campo Grande?",
        "E para Dourados?",
        "Como eu compro?",
    ],
    [
        "Meu violão do pedido 1 veio quebrado. Telefone (67) 98432-1098.",
        "Em quanto tempo vão me responder?",
        "Posso trocar por outro?",
        "Ok, obrigado.",
    ],
]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def converse(agent: Agent, messages: list[str]) -> list[Turn]:
    session = agent.new_session()
    return [agent.reply(session, text) for text in messages]


def run_burst(
    client: Any,
    data: StoreData,
    journal: Any,
    spend: Spend,
    done: list[list[Turn]] | None = None,
) -> list[list[Turn]]:
    """Pass `done` to keep the finished conversations if the budget check fails afterwards."""
    agents = [Agent(client, data, journal) for _ in CONVERSATIONS]
    with ThreadPoolExecutor(max_workers=len(CONVERSATIONS)) as pool:
        futures = [
            pool.submit(converse, agent, messages)
            for agent, messages in zip(agents, CONVERSATIONS, strict=True)
        ]
        conversations = [future.result() for future in futures]
    if done is not None:
        done.extend(conversations)
    for agent, turns in zip(agents, conversations, strict=True):
        spend.charge(agent.model, turns)  # charged after the fact: a burst cannot be stopped midway
    return conversations


def summarize(conversations: list[list[Turn]], spend: Spend, model: str) -> str:
    turns = [turn for conversation in conversations for turn in conversation]
    seconds = [turn.seconds for turn in turns]
    fallbacks = sum(turn.text == FALLBACK_TEXT for turn in turns)
    fresh, cached, output, written = spend.tokens
    per_conversation = spend.spent / len(conversations)
    return "\n".join(
        [
            "## Burst\n",
            f"{len(conversations)} simultaneous conversations of {len(CONVERSATIONS[0])} messages "
            f"on `{model}`.\n",
            f"- Time per answer: median {statistics.median(seconds):.2f}s, "
            f"p95 {percentile(seconds, 0.95):.2f}s",
            f"- Answers that fell back to the contingency text: {fallbacks}/{len(turns)}",
            f"- Tokens: {fresh} input, {cached} cached, {output} output",
            f"- Estimated cost: US$ {spend.spent:.4f} (US$ {per_conversation:.4f} per conversation)",
        ]
    )


def main(argv: list[str] | None = None, client_factory: Callable[[], Any] = make_client) -> int:
    parser = argparse.ArgumentParser(description="Simultaneous conversations")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET)
    args = parser.parse_args(argv)
    require_key(ROOT)

    data = StoreData.load(ROOT / "data")
    spend = Spend(args.budget)
    finished: list[list[Turn]] = []
    model = os.environ.get("EMPORIO_MODEL", DEFAULT_MODEL)
    try:
        conversations = run_burst(client_factory(), data, journal_for("burst"), spend, finished)
    except BudgetExceeded as stop:
        print(stop, file=sys.stderr)
        if finished:
            write_results("burst", summarize(finished, spend, model), partial=True)
        return 1
    except anthropic.AuthenticationError:
        print("Chave inválida: confira ANTHROPIC_API_KEY no .env.", file=sys.stderr)
        return 1
    summary = summarize(conversations, spend, model)
    print(summary)
    write_results("burst", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
