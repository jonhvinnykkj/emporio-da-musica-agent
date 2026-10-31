"""Terminal chat. Text in, text out, like a messaging channel."""

import argparse
import json
import uuid
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from emporio.agent import Turn, build_agent

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / ".emporio" / "emporio.sqlite3"
EXIT_WORDS = {"/sair", "sair", "exit", "quit"}
MISSING_KEY = "Chave inválida ou ausente: defina ANTHROPIC_API_KEY no arquivo .env (veja .env.example)."


def print_trace(turn: Turn) -> None:
    for call in turn.tool_calls:
        print(f"  [tool] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")
    if turn.guard_fired:
        print("  [guard] resposta com valor sem fonte foi devolvida ao modelo")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atendimento da Empório da Música")
    parser.add_argument("--session", help="retoma uma conversa anterior pelo id")
    parser.add_argument("--trace", action="store_true", help="mostra as ferramentas usadas")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    agent = build_agent(DATA_DIR, DB_PATH)
    session_id = args.session or uuid.uuid4().hex[:8]
    print(f"Empório da Música (sessão {session_id}). Digite /sair para encerrar.\n")

    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.lower() in EXIT_WORDS:
            return
        if not text:
            continue
        try:
            turn = agent.reply(session_id, text)
        except anthropic.AuthenticationError:
            raise SystemExit(MISSING_KEY)
        except TypeError as error:
            # The SDK raises TypeError, not an API error, when it finds no credential at all.
            if "authentication" not in str(error):
                raise
            raise SystemExit(MISSING_KEY)
        except anthropic.APIError as error:
            print(f"Tom: Estou com instabilidade agora, tenta de novo em instantes. ({type(error).__name__})\n")
            continue
        if args.trace:
            print_trace(turn)
        print(f"Tom: {turn.text}\n")


if __name__ == "__main__":
    main()
