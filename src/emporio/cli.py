"""Terminal chat. Text in, text out, like a messaging channel."""

import argparse
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from emporio.agent import REQUEST_TIMEOUT, Agent, Turn, configured_clock
from emporio.catalog import DataError
from emporio.data_audit import find_inconsistencies
from emporio.journal import Journal
from emporio.tools import StoreData

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
JOURNAL_PATH: Path | None = ROOT / ".emporio" / "journal.jsonl"
EXIT_WORDS = {"/sair", "sair", "exit", "quit"}
MISSING_KEY = "Chave inválida ou ausente: defina ANTHROPIC_API_KEY no arquivo .env (veja .env.example)."


def make_client() -> Any:
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT)


def print_trace(turn: Turn, write: Callable[[str], None]) -> None:
    for call in turn.tool_calls:
        write(f"  [ferramenta] {call.name} {call.arguments}{' (erro)' if call.is_error else ''}")
    if turn.guard_fired:
        write("  [trava] resposta com valor sem fonte foi devolvida ao modelo")
    write(
        f"  [tokens] entrada {turn.input_tokens}, cache {turn.cached_tokens}, "
        f"saída {turn.output_tokens}; {turn.seconds:.1f}s"
    )


def run_chat(
    agent: Agent,
    debug: bool,
    read: Callable[[str], str] | None = None,
    write: Callable[[str], None] = print,
) -> None:
    read = read or input
    session = agent.new_session()
    while True:
        try:
            text = read("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            return
        if text.lower() in EXIT_WORDS:
            return
        if not text:
            continue
        try:
            turn = agent.reply(session, text)
        except anthropic.AuthenticationError:
            raise SystemExit(MISSING_KEY) from None
        if debug:
            print_trace(turn, write)
        write(f"Tom: {turn.text}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Atendimento da Empório da Música")
    parser.add_argument("--debug", action="store_true", help="mostra ferramentas, trava, tokens e tempo")
    args = parser.parse_args(argv)

    # Only the project's own .env is used; it wins over any key already in the environment.
    load_dotenv(ROOT / ".env", override=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(MISSING_KEY)
    try:
        data = StoreData.load(DATA_DIR)
    except DataError as error:
        raise SystemExit(f"Erro nos dados da loja: {error}") from None

    findings = find_inconsistencies(data.catalog, data.orders)
    print(f"Empório da Música: {len(findings)} inconsistências nos dados. Digite /sair para encerrar.")
    if args.debug:
        for finding in findings:
            print(f"  - {finding}")
    print()
    agent = Agent(make_client(), data, Journal(JOURNAL_PATH), configured_clock())
    run_chat(agent, args.debug)


if __name__ == "__main__":
    main()
