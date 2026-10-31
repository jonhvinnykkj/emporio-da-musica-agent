"""Record real conversations into examples/, with the tools each answer used.

uv run python scripts/record_examples.py

Needs a .env with ANTHROPIC_API_KEY. Scenarios 5, 4, 12, 16 and 20 of section 8 of docs/logica-ideal.md,
with the store clock pinned to the one each scenario declares.
"""

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from emporio.agent import REQUEST_TIMEOUT, Agent, Turn
from emporio.journal import Journal
from emporio.tools import StoreData
from evals.cases import CASES, Case

ROOT = Path(__file__).resolve().parents[1]
MISSING_ENV = (
    "Arquivo .env não encontrado ou sem ANTHROPIC_API_KEY. Crie {path} a partir de .env.example. "
    "Nenhuma conversa foi gravada."
)
# (file name, case id in evals/cases.py, what the example shows)
EXAMPLES = [
    ("01-violoes-ate-1000", "05_filter_up_to_1000", "Category and price filter, with the total."),
    ("02-takamine-sem-promocao", "04_price_without_expired_promotion", "An inactive promotion is ignored."),
    ("03-pedido-atrasado", "12_shipped_late_order", "Order lookup by phone, overdue delivery, handoff."),
    ("04-arrependimento", "16_regret_after_delivery", "Return policy on an order; what is unconfirmed."),
    ("05-pressao-e-prompt", "20_pressure_and_prompt_request", "Pressure, off-topic, prompt request."),
]


def find_case(case_id: str) -> Case:
    return next(case for case in CASES if case.id == case_id)


def render(title: str, summary: str, case: Case, exchanges: list[tuple[str, Turn]], model: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"**Shows:** {summary}",
        "",
        f"Recorded by `scripts/record_examples.py` (scenario `{case.id}`) on model `{model}`, "
        f"with the store clock pinned to {case.now:%A %Y-%m-%d %H:%M}.",
        "",
    ]
    for text, turn in exchanges:
        lines += [f"**Cliente:** {text}", ""]
        for call in turn.tool_calls:
            marker = " (erro)" if call.is_error else ""
            lines.append(f"> `{call.name}({json.dumps(call.arguments, ensure_ascii=False)})`{marker}")
        if turn.tool_calls:
            lines.append("")
        lines += [f"**Tom:** {turn.text}", "", "---", ""]
    return "\n".join(lines)


def require_key(root: Path) -> None:
    if not (root / ".env").exists():
        raise SystemExit(MISSING_ENV.format(path=root / ".env"))
    load_dotenv(root / ".env", override=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(MISSING_ENV.format(path=root / ".env"))


def make_client() -> Any:
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT)


def record(client: Any, data: StoreData, journal: Journal, root: Path) -> list[Path]:
    written = []
    for name, case_id, summary in EXAMPLES:
        case = find_case(case_id)
        agent = Agent(client, data, journal, clock=lambda case=case: case.now)
        session = agent.new_session()
        exchanges = [(text, agent.reply(session, text)) for text in case.turns]
        title = name.split("-", 1)[1].replace("-", " ").capitalize()
        path = root / "examples" / f"{name}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(render(title, summary, case, exchanges, agent.model), encoding="utf-8")
        written.append(path)
    return written


def main(client_factory: Callable[[], Any] = make_client, root: Path = ROOT) -> int:
    require_key(root)
    data = StoreData.load(root / "data")
    journal = Journal(root / ".emporio" / "examples.jsonl")
    try:
        paths = record(client_factory(), data, journal, root)
    except anthropic.AuthenticationError:
        print("Chave inválida: confira ANTHROPIC_API_KEY no .env.", file=sys.stderr)
        return 1
    for path in paths:
        print(f"wrote {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
