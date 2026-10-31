"""The agent loop: call the model, run the tools it asks for, check the final answer."""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import anthropic

from emporio.guardrails import unsupported_amounts
from emporio.hours import store_now
from emporio.prompts import build_stable_prompt, build_system
from emporio.store import Store
from emporio.tools import StoreData, Toolbox, tool_definitions

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
MAX_TOKENS = 4096
MAX_STEPS = 8
FALLBACK_TEXT = (
    "Tive um probleminha para concluir seu atendimento por aqui. "
    "Você pode falar com a equipe pelo telefone (67) 3341-4444?"
)
UNVERIFIED_AMOUNT_TEXT = (
    "Prefiro confirmar esse valor com a equipe antes de te passar, para não informar nada errado. "
    "Quer que eu abra um chamado para eles te retornarem?"
)
GUARD_CORRECTION = (
    "[Verificação automática do sistema, não é mensagem do cliente] Estes valores da sua resposta não vieram de "
    "nenhuma ferramenta neste turno: {amounts}. Consulte a ferramenta adequada ou reescreva sem esses valores."
)


def configured_clock() -> Callable[[], datetime]:
    pinned = os.environ.get("EMPORIO_NOW")
    return (lambda: datetime.fromisoformat(pinned)) if pinned else store_now


@dataclass
class ToolCall:
    name: str
    arguments: dict
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


class Agent:
    def __init__(self, client, data: StoreData, store: Store, clock: Callable[[], datetime] = store_now):
        self.client = client
        self.data = data
        self.store = store
        self.clock = clock
        self.model = os.environ.get("EMPORIO_MODEL", DEFAULT_MODEL)
        self.effort = os.environ.get("EMPORIO_EFFORT", DEFAULT_EFFORT)
        self.tools = tool_definitions(list(data.catalog.categories.values()))
        self.stable_prompt = build_stable_prompt(data.catalog.overview(), data.manual.contents())

    def reply(self, session_id: str, text: str) -> Turn:
        now = self.clock()
        system = build_system(self.stable_prompt, now)
        toolbox = Toolbox(self.data, self.store, session_id, now.date())
        # Earlier turns are kept as text only: tool results go stale, so facts are fetched again.
        messages = [*self.store.history(session_id), {"role": "user", "content": text}]
        turn = Turn()
        evidence = [text]

        for _ in range(MAX_STEPS):
            response = self._call_model(system, messages, turn)
            if response.stop_reason == "refusal":
                break
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if tool_uses:
                results = [self._run_tool(toolbox, block, turn, evidence) for block in tool_uses]
                messages.append({"role": "user", "content": results})
                continue
            answer = "".join(block.text for block in response.content if block.type == "text").strip()
            unsupported = unsupported_amounts(answer, evidence)
            if not unsupported:
                turn.text = answer
                break
            if turn.guard_fired:
                turn.text = UNVERIFIED_AMOUNT_TEXT
                break
            turn.guard_fired = True
            listed = ", ".join(str(amount) for amount in sorted(unsupported))
            messages.append({"role": "user", "content": GUARD_CORRECTION.format(amounts=listed)})

        turn.text = turn.text or FALLBACK_TEXT
        self.store.add_exchange(session_id, text, turn.text)
        return turn

    def _call_model(self, system: list[dict], messages: list[dict], turn: Turn):
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=self.tools,
            messages=messages,
            output_config={"effort": self.effort},
        )
        turn.input_tokens += response.usage.input_tokens
        turn.cached_tokens += response.usage.cache_read_input_tokens or 0
        turn.output_tokens += response.usage.output_tokens
        return response

    @staticmethod
    def _run_tool(toolbox: Toolbox, block, turn: Turn, evidence: list[str]) -> dict:
        output, is_error = toolbox.run(block.name, block.input)
        turn.tool_calls.append(ToolCall(block.name, block.input, output, is_error))
        evidence.append(output)
        return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}


def build_agent(data_dir, db_path) -> Agent:
    return Agent(anthropic.Anthropic(), StoreData.load(data_dir), Store(db_path), configured_clock())
