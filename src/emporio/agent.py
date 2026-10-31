"""The agent loop: call the model, run the tools it asks for, check the final answer."""

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import anthropic

from emporio.guardrails import unsupported_amounts
from emporio.hours import store_now
from emporio.journal import Journal
from emporio.prompts import build_system, build_turn_content
from emporio.tools import StoreData, Toolbox, tool_definitions

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"
MAX_TOKENS = 4096
MAX_TOOL_CALLS = 5
MAX_MESSAGE_CHARS = 2000
REQUEST_TIMEOUT = 30
FALLBACK_TEXT = (
    "Tive um probleminha para concluir seu atendimento por aqui. "
    "Você pode falar com a equipe pelo telefone (67) 3341-4444 ou pelo WhatsApp (67) 3321-4500."
)
SAFE_TEXT = (
    "Prefiro não te passar um valor sem ter certeza de que está certo. "
    "Já deixei seu caso com a equipe, que vai te responder com o valor correto. "
    "Se preferir, fale pelo telefone (67) 3341-4444."
)
EMPTY_TEXT = "Não recebi sua mensagem. Pode escrever de novo?"
TOO_LONG_TEXT = f"Sua mensagem ficou muito longa. Pode resumir em até {MAX_MESSAGE_CHARS} caracteres?"
GUARD_CORRECTION = (
    "[Verificação automática do sistema, não é mensagem do cliente] Estes valores da sua resposta "
    "não vieram de nenhuma ferramenta neste turno: {amounts}. "
    "Consulte a ferramenta adequada ou reescreva sem esses valores."
)


def configured_clock() -> Callable[[], datetime]:
    pinned = os.environ.get("EMPORIO_NOW")
    return (lambda: datetime.fromisoformat(pinned)) if pinned else store_now


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    guard_fired: bool = False
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


@dataclass
class Session:
    """One conversation. `messages` is append-only, except when a failed turn is rolled back."""

    id: str
    toolbox: Toolbox
    messages: list[dict[str, Any]] = field(default_factory=list)


class TurnFailed(Exception):
    """The turn cannot produce an answer; the conversation goes back to where the turn started."""


class AmountsWithheld(Exception):
    """The reply still had amounts without a source after one correction."""

    def __init__(self, amounts: set[Decimal]):
        super().__init__(amounts)
        self.amounts = amounts


class Agent:
    def __init__(
        self, client: Any, data: StoreData, journal: Journal, clock: Callable[[], datetime] = store_now
    ):
        self.client = client
        self.data = data
        self.journal = journal
        self.clock = clock
        self.model = os.environ.get("EMPORIO_MODEL", DEFAULT_MODEL)
        self.effort = os.environ.get("EMPORIO_EFFORT", DEFAULT_EFFORT)
        self.tools = tool_definitions(list(data.catalog.categories.values()))
        self.system = build_system(data)

    def new_session(self) -> Session:
        session_id = uuid.uuid4().hex[:8]
        return Session(session_id, Toolbox(self.data, self.journal, session_id, self.clock))

    def reply(self, session: Session, text: str) -> Turn:
        turn = Turn()
        if not text.strip():
            turn.text = EMPTY_TEXT
            return turn
        if len(text) > MAX_MESSAGE_CHARS:
            turn.text = TOO_LONG_TEXT
            return turn

        started = time.perf_counter()
        start = len(session.messages)
        session.messages.append({"role": "user", "content": build_turn_content(self.clock(), text)})
        try:
            turn.text = self._converse(session, text, turn)
        except anthropic.AuthenticationError:
            del session.messages[start:]
            raise
        except (anthropic.APIError, TurnFailed) as error:
            del session.messages[start:]
            turn.text = FALLBACK_TEXT
            self.journal.record("erro", session.id, {"motivo": type(error).__name__, "detalhe": str(error)})
        except AmountsWithheld as withheld:
            # Keep the customer's message and the safe reply, drop the unverified answer.
            customer_message = session.messages[start]
            del session.messages[start:]
            session.messages += [customer_message, {"role": "assistant", "content": SAFE_TEXT}]
            turn.text = SAFE_TEXT
            listed = ", ".join(str(amount) for amount in sorted(withheld.amounts))
            summary = f"Resposta com valor sem fonte bloqueada ({listed}). Cliente: {text}"
            session.toolbox.hand_off("outro", summary)
        except Exception as error:  # noqa: BLE001 - any tool or data failure must not kill the chat
            del session.messages[start:]
            turn.text = FALLBACK_TEXT
            self.journal.record("erro", session.id, {"motivo": type(error).__name__, "detalhe": str(error)})

        turn.seconds = time.perf_counter() - started
        self._log(session, text, turn)
        return turn

    def _converse(self, session: Session, text: str, turn: Turn) -> str:
        evidence = [text, self.data.manual]
        while True:
            response = self._call_model(session, turn)
            if response.stop_reason in ("refusal", "max_tokens"):
                raise TurnFailed(response.stop_reason)
            # The whole content goes back as it came, thinking blocks included.
            session.messages.append({"role": "assistant", "content": response.content})
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if tool_uses:
                if len(turn.tool_calls) + len(tool_uses) > MAX_TOOL_CALLS:
                    raise TurnFailed("tool call limit")
                results = [self._run_tool(session.toolbox, block, turn, evidence) for block in tool_uses]
                session.messages.append({"role": "user", "content": results})
                continue
            answer = "".join(block.text for block in response.content if block.type == "text").strip()
            if not answer:
                raise TurnFailed("empty answer")
            unsupported = unsupported_amounts(answer, evidence)
            if not unsupported:
                return answer
            if turn.guard_fired:
                raise AmountsWithheld(unsupported)
            turn.guard_fired = True
            listed = ", ".join(str(amount) for amount in sorted(unsupported))
            correction = GUARD_CORRECTION.format(amounts=listed)
            session.messages.append({"role": "user", "content": [{"type": "text", "text": correction}]})

    def _call_model(self, session: Session, turn: Turn) -> Any:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=session.messages,
            output_config={"effort": self.effort},
        )
        turn.input_tokens += response.usage.input_tokens
        turn.cached_tokens += response.usage.cache_read_input_tokens or 0
        turn.output_tokens += response.usage.output_tokens
        return response

    @staticmethod
    def _run_tool(toolbox: Toolbox, block: Any, turn: Turn, evidence: list[str]) -> dict[str, Any]:
        output, is_error = toolbox.run(block.name, block.input)
        turn.tool_calls.append(ToolCall(block.name, block.input, output, is_error))
        evidence.append(output)
        return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}

    def _log(self, session: Session, text: str, turn: Turn) -> None:
        self.journal.record(
            "mensagem",
            session.id,
            {
                "cliente": text,
                "resposta": turn.text,
                "ferramentas": [call.name for call in turn.tool_calls],
                "trava": turn.guard_fired,
                "tokens_entrada": turn.input_tokens,
                "tokens_cache": turn.cached_tokens,
                "tokens_saida": turn.output_tokens,
                "segundos": turn.seconds,
            },
        )
