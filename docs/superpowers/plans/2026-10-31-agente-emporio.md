# Agente da Empório da Música: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o rascunho local no sistema de `docs/logica-ideal.md`, provado por testes automáticos, estresse e conversas reais com o modelo.

**Architecture:** Um agente único em laço simples, com 4 ferramentas tipadas e o manual inteiro no contexto fixo. O modelo conduz a conversa; o código decide preço, disponibilidade, identidade, relógio e limites. O estado da conversa fica em memória, e o registro em JSONL.

**Tech Stack:** Python 3.12, uv, `anthropic`, `pypdf`, `python-dotenv`, `tzdata`. Dev: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `mypy`.

**Spec:** `docs/logica-ideal.md`

## Global Constraints

- Ferramentas, exatamente 4: `buscar_produtos`, `calcular_compra`, `consultar_pedido`, `encaminhar_para_equipe`. Nenhuma escreve em dados da loja.
- Modelo padrão `claude-haiku-5-5`, esforço `low`, trocáveis por `EMPORIO_MODEL` e `EMPORIO_EFFORT`.
- Limites: 5 chamadas de ferramenta por turno; mensagem de até 2.000 caracteres; busca mostra até 5 itens e informa o total.
- `disponivel = status == "active" and estoque > 0`. Status vence estoque.
- Promoção só com `is_active=1`. PIX de 5% nunca soma com promoção.
- Parcelas pela seção 3.1: até 3x com mínimo de R$ 50; 4x a 6x com R$ 80; 7x a 12x com R$ 100.
- Frete em Campo Grande: grátis a partir de R$ 500 sobre o valor final; abaixo disso, R$ 35. Outras cidades: nunca dar valor.
- Identidade: número do pedido mais telefone. E-mail não identifica ninguém. Três falhas por sessão bloqueiam a consulta.
- `requer_atencao`: enviado com previsão vencida, ou pendente/confirmado há mais de 15 dias corridos.
- Prazo de 24 horas úteis só em reclamação.
- Fuso `America/Campo_Grande`. Feriados nacionais em lista no código, com Sexta-feira Santa calculada.
- Canais: telefone (67) 3341-4444, WhatsApp (67) 3321-4500, e-mail contato@emporiodamusica.com.br.
- Persona "Tom", assistente virtual, sem se passar por pessoa.
- Idiomas: cliente, prompt e ferramentas em português do Brasil; código, commits e README em inglês.
- Sem dependências fora da lista. Sem LangChain, banco de dados ou embeddings.
- Git: autor `João Vinnycius <jonhv.dev@gmail.com>`, sem force-push, com a linha `Co-Authored-By` nos commits. Nada é publicado sem OK do candidato.
- Toda tarefa termina com `uv run pytest`, `uv run ruff check .` e `uv run mypy src` limpos.

## Review Focus

Cinco falhas que a lógica implica e nenhum cenário cobre. Cada uma tem teste na tarefa dona do código.

1. A API cai no meio de um turno: a conversa continua utilizável, sem pedido de ferramenta sem resposta no histórico (Tarefa 4).
2. Valor escrito como `R$ 1199.80`, com ponto decimal: a trava lê R$ 1.199,80, não 119.980 (Tarefa 4).
3. Telefone digitado de outro jeito (`+55 67 99654-7821`, `067 99654 7821`): é aceito, sem aceitar número parcial (Tarefa 2).
4. Depois de três falhas em um pedido, o cliente tenta outro pedido: continua bloqueado na sessão (Tarefa 3).
5. O cliente escreve o telefone ou o e-mail no meio da frase: o registro em JSONL não guarda esse dado aberto (Tarefa 3).

---

## Equipe e custo

| Papel | Agente | Modelo | Onde |
|---|---|---|---|
| Orquestrador | Sessão principal | Opus | Coordena e decide; não lê código sem necessidade |
| 5 construtores | Um novo por tarefa | Sonnet, esforço médio | Tarefas 1 a 5 |
| 5 revisores | Um novo por tarefa, sem ter visto a construção | Sonnet, esforço baixo | Uma rodada por tarefa; só achados graves ou médios |
| 1 caçador de bugs | Lê a lógica, não o código | Sonnet | Tarefa 6 |
| 1 revisor final | Orçamento de leitura fixo | Sonnet | Tarefa 7 |

Regras de custo: cada agente recebe só a própria tarefa; sem revisão em loop; o estresse da Tarefa 5 não gasta modelo; a Tarefa 6 tem teto de US$ 3 em chamadas de API. A estimativa é de 2 a 3 milhões de tokens em agentes.

## Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/emporio/catalog.py` | Leitura de CSV, disponibilidade e busca |
| `src/emporio/pricing.py` | Dinheiro, PIX, parcelas e frete |
| `src/emporio/orders.py` | Identidade e visão segura do pedido |
| `src/emporio/hours.py` | Relógio, feriados e horário |
| `src/emporio/manual.py` (novo) | Texto do manual e bloco de erratas |
| `src/emporio/data_audit.py` (novo) | Avisos de inconsistência no carregamento |
| `src/emporio/journal.py` (novo) | Registro JSONL com dados mascarados |
| `src/emporio/tools.py` | As 4 ferramentas e o despacho |
| `src/emporio/guardrails.py` | Trava de valores em R$ |
| `src/emporio/prompts.py` | Prompt fixo |
| `src/emporio/agent.py` | Laço do agente e sessão |
| `src/emporio/cli.py` | Terminal |
| `evals/` | Cenários, red team e carga com o modelo real |

Saem: `src/emporio/policies.py`, `src/emporio/store.py`, `scripts/audit_data.py`.

---

### Task 1: Base de qualidade, catálogo e preços

**Files:**
- Modify: `pyproject.toml`, `src/emporio/catalog.py`, `src/emporio/pricing.py`
- Create: `.github/workflows/ci.yml`
- Test: `tests/test_catalog.py`, `tests/test_pricing.py`

**Interfaces:**
- Consumes: nada.
- Produces: `DataError(Exception)`; `Catalog(data_dir: Path)` com `.products: dict[int, Product]` e `.categories: dict[int, str]`; `Catalog.search(query=None, category=None, min_price=None, max_price=None, strings=None, electronics=None, on_sale=False, limit=5) -> dict` com `total_encontrado`, `mostrando`, `produtos` e, quando couber, `correspondencia`, `indisponiveis`, `alternativas`, `categoria_sem_produtos`; `Catalog.overview() -> str`; `Quote.pix_total(quantity: int) -> Decimal`; `brl`, `to_money`, `max_installments`, `installment_text`, `metro_shipping`.

- [ ] **Step 1: Ajustar `pyproject.toml`.** Remover `holidays`. Adicionar ao grupo dev `pytest-cov`, `hypothesis`, `ruff`, `mypy`. Configurar ruff (`E,F,I,B,UP`, linha 110), mypy (`strict = true` em `src`) e cobertura mínima de 90% em `src/emporio`.

- [ ] **Step 2: Escrever os testes novos que falham**

```python
def test_list_shows_five_and_reports_the_total(catalog):
    result = catalog.search(category="Violões", max_price=1000)
    assert (result["total_encontrado"], result["mostrando"]) == (12, 5)

def test_on_sale_lists_the_four_active_promotions(catalog):
    result = catalog.search(on_sale=True, limit=50)
    assert {item["id"] for item in result["produtos"]} == {90, 94, 121, 127}

def test_every_item_says_if_a_promotion_is_active(catalog):
    item = catalog.search(query="takamine gd20")["produtos"][0]
    assert item["promocao_ativa"] is False

def test_flagged_product_hides_description_and_specs(catalog):
    data = catalog.products[135].to_dict()
    assert "descricao" not in data and "especificacoes" not in data

def test_inverted_price_range_is_empty(catalog):
    assert catalog.search(min_price=1000, max_price=500)["total_encontrado"] == 0

def test_nonsense_query_finds_nothing(catalog):
    assert catalog.search(query="xyzzy")["correspondencia"] == "nenhuma"

def test_missing_file_names_the_file(tmp_path):
    with pytest.raises(DataError, match="categories.csv"):
        Catalog(tmp_path)

@given(st.decimals(min_value="0.01", max_value="100000", places=2))
def test_installment_never_goes_below_the_floor(amount):
    count = max_installments(amount)
    floor = next(value for limit, value in INSTALLMENT_TIERS if count <= limit)
    assert count == 1 or amount / count >= floor
```

- [ ] **Step 3: Rodar e ver falhar.** Run: `uv run pytest tests/test_catalog.py tests/test_pricing.py -v`. Expected: FAIL nos testes acima.

- [ ] **Step 4: Implementar em `catalog.py`.** Adicionar `DataError`, levantada por `read_csv` com o nome do arquivo em caso de arquivo ausente, coluna ausente ou valor inválido. Adicionar `on_sale` a `search`, com `limit=5`. Incluir `promocao_ativa` em `Product.to_dict`. Esconder `especificacoes` junto da descrição nos produtos marcados. Remover `promotions_report` e `expired_promotions`.

- [ ] **Step 5: Criar `.github/workflows/ci.yml`.** Em push e pull request: instalar uv, `uv sync`, ruff, mypy e pytest com cobertura. Nenhum job usa chave de API.

- [ ] **Step 6: Verificar.** Run: `uv run pytest tests/test_catalog.py tests/test_pricing.py -v && uv run ruff check . && uv run mypy src/emporio/catalog.py src/emporio/pricing.py`. Expected: tudo PASS.

- [ ] **Step 7: Commit.** `git commit -m "refactor: align catalog and pricing with the approved logic"`

### Task 2: Pedidos e relógio

**Files:**
- Modify: `src/emporio/orders.py`, `src/emporio/hours.py`
- Test: `tests/test_orders.py`, `tests/test_hours.py`

**Interfaces:**
- Consumes: `Catalog`, `read_csv`, `brl`.
- Produces: `OrderBook(data_dir, catalog)`; `OrderBook.verified_order(order_id: int, phone: str) -> Order | None`; `OrderBook.view(order: Order, today: date) -> dict` com `pedido`, `cliente_primeiro_nome`, `data_do_pedido`, `status`, `valor_registrado`, `pagamento`, `itens`, `dias_desde_a_compra`, `requer_atencao` e, quando existirem, `codigo_de_rastreio`, `previsao_de_entrega`, `dias_desde_a_previsao`, `motivo_cancelamento`; `hours.store_now() -> datetime`; `hours.is_holiday(day: date) -> bool`; `hours.describe(now: datetime) -> str`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("phone", [
    "(67) 99654-7821", "67996547821", "996547821",
    "+55 67 99654-7821", "5567996547821", "067 99654 7821",
])
def test_phone_formats_are_accepted(book, phone):
    assert book.verified_order(8, phone).id == 8

@pytest.mark.parametrize("phone", ["96547821", "7821", "", "anacarol.ferreira@coldmail.com", "(67) 99812-3456"])
def test_partial_or_wrong_contact_is_refused(book, phone):
    assert book.verified_order(8, phone) is None

def test_order_8_is_245_days_past_its_estimate(book):
    view = book.view(book.orders[8], date(2026, 10, 31))
    assert view["dias_desde_a_previsao"] == 245 and view["requer_atencao"] is True

@pytest.mark.parametrize("days_old, expected", [(15, False), (16, True)])
def test_stalled_order_boundary(book, days_old, expected):
    order = book.orders[13]
    today = date.fromordinal(order.date.toordinal() + days_old)
    assert book.view(order, today)["requer_atencao"] is expected

def test_shipped_order_is_fine_on_the_estimated_day(book):
    order = book.orders[8]
    assert book.view(order, order.estimated_delivery)["requer_atencao"] is False

def test_view_uses_recorded_value_and_plain_status(book):
    view = book.view(book.orders[13], date(2026, 3, 13))
    assert view["valor_registrado"] == "R$ 1.899,00" and view["status"] == "Pendente"

@pytest.mark.parametrize("day", [date(2026, 11, 2), date(2026, 11, 20), date(2026, 4, 3), date(2027, 3, 26)])
def test_national_holidays_include_finados_and_good_friday(day):
    assert is_holiday(day)

def test_saturday_afternoon_before_finados():
    assert "terça-feira, 03/11 às 09:00" in describe(datetime(2026, 10, 31, 14, 0))
```

- [ ] **Step 2: Rodar e ver falhar.** Run: `uv run pytest tests/test_orders.py tests/test_hours.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar em `orders.py`.** Trocar a verificação para telefone apenas: remover zero à esquerda, remover `55` só com 13 dígitos e aceitar igualdade com os 11 dígitos do cadastro ou com os 9 finais. Trocar `alerta` por `requer_atencao` com as regras dos Global Constraints. Rótulos de status: Pendente, Confirmado, Enviado, Entregue, Cancelado. Remover `return_decision` e as constantes de prazo: a regra está no manual e os dias vêm prontos em `view`.

- [ ] **Step 4: Implementar em `hours.py`.** Remover `holidays`. Feriados fixos: 01/01, 21/04, 01/05, 07/09, 12/10, 02/11, 15/11, 20/11, 25/12. Sexta-feira Santa: dois dias antes da Páscoa, calculada com o algoritmo gregoriano anônimo. Testar a Páscoa de 2026 (05/04) e 2027 (28/03).

- [ ] **Step 5: Verificar.** Run: `uv run pytest tests/test_orders.py tests/test_hours.py -v && uv run ruff check . && uv run mypy src/emporio/orders.py src/emporio/hours.py`. Expected: tudo PASS.

- [ ] **Step 6: Commit.** `git commit -m "refactor: phone-only identity, attention flag and in-code holidays"`

### Task 3: Manual, auditoria, registro e ferramentas

**Files:**
- Create: `src/emporio/manual.py`, `src/emporio/data_audit.py`, `src/emporio/journal.py`
- Delete: `src/emporio/policies.py`, `src/emporio/store.py`, `scripts/audit_data.py`, `tests/test_policies.py`
- Modify: `src/emporio/tools.py`
- Test: `tests/test_manual.py`, `tests/test_data_audit.py`, `tests/test_journal.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `Catalog`, `OrderBook`, `DataError`, `brl`, `installment_text`, `metro_shipping`, `Quote.pix_total`.
- Produces: `load_manual(pdf_path: Path) -> str`; `find_inconsistencies(catalog: Catalog, book: OrderBook) -> list[str]`; `mask_contact(text: str) -> str`; `Journal(path: Path | None)` com `.record(kind: str, session_id: str, payload: dict) -> None`, seguro entre threads e que nunca interrompe o atendimento se a gravação falhar; `StoreData(catalog, orders, manual)` com `StoreData.load(data_dir)`; `Toolbox(data, journal, session_id, clock: Callable[[], datetime])` com `.run(name: str, arguments: dict) -> tuple[str, bool]`, lendo o relógio a cada chamada para uma sessão poder passar da meia-noite; `tool_definitions(category_names: list[str]) -> list[dict]`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_manual_keeps_tables_and_lines(manual_text):
    assert "Cartão de Crédito | Até 12x sem juros" in manual_text
    assert "Página 4" not in manual_text

def test_errata_resolves_the_contradictions(manual_text):
    for fact in ("(67) 3341-4444", "(67) 3321-4500", "contato@emporiodamusica.com.br", "3.1"):
        assert fact in manual_text

def test_audit_reports_the_known_traps(catalog, book):
    report = "\n".join(find_inconsistencies(catalog, book))
    for fragment in ("136", "130", "pedido 3", "pedido 20", "categoria"):
        assert fragment in report

def test_mask_hides_phone_and_email_inside_a_sentence():
    masked = mask_contact("sou a Ana, (67) 99654-7821 e ana@coldmail.com")
    assert "99654" not in masked and "coldmail" not in masked and "7821" in masked

def test_journal_write_failure_does_not_raise(tmp_path):
    Journal(tmp_path).record("mensagem", "s1", {"texto": "oi"})  # path is a directory

def test_lock_applies_to_every_order_in_the_session(box):
    for _ in range(3):
        call(box, "consultar_pedido", numero_pedido=8, telefone="(67) 90000-0000")
    blocked, _ = call(box, "consultar_pedido", numero_pedido=4, telefone="(67) 99812-3456")
    assert "status" not in blocked and blocked["bloqueado"] is True

def test_wrong_phone_and_missing_order_get_the_same_answer(box):
    assert call(box, "consultar_pedido", numero_pedido=999, telefone="(67) 99654-7821")[0] == \
           call(box, "consultar_pedido", numero_pedido=8, telefone="(67) 90000-0000")[0]

def test_only_complaints_promise_a_return_time(box):
    assert call(box, "encaminhar_para_equipe", motivo="reclamacao", resumo="x")[0]["prazo_de_retorno"] == "24 horas úteis"
    assert "prazo_de_retorno" not in call(box, "encaminhar_para_equipe", motivo="sem_resposta", resumo="x")[0]

@pytest.mark.parametrize("quantity", [0, -1, 1000])
def test_invalid_quantity_is_reported(box, quantity):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": quantity}])
    assert result["itens"] == [] and result["problemas"]

def test_compra_rounds_pix_on_the_line(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": 2}], cidade="Campo Grande")
    assert result["total_no_pix_com_frete"] == "R$ 1.139,81"

def test_compra_never_prices_shipping_for_other_cities(box):
    result, _ = call(box, "calcular_compra", itens=[{"produto_id": 81, "quantidade": 1}], cidade="Dourados")
    assert "total_com_frete" not in result
```

- [ ] **Step 2: Rodar e ver falhar.** Run: `uv run pytest tests/test_manual.py tests/test_data_audit.py tests/test_journal.py tests/test_tools.py -v`. Expected: FAIL.

- [ ] **Step 3: Criar `manual.py`.** `load_manual` extrai com `extraction_mode="layout"`, remove cabeçalhos e rodapés de página, troca lacunas de coluna por ` | ` e acrescenta `ERRATA`: telefone e WhatsApp, e-mail sem acento, 3.1 prevalece sobre a tabela, parcela mínima de R$ 50 até 3x, 30 dias de 4.2 e 90 dias de 8.1 são prazos diferentes, sem lojas parceiras, catálogo menor que o citado. PDF ausente levanta `DataError`.

- [ ] **Step 4: Criar `data_audit.py`.** Porta as verificações de `scripts/audit_data.py` para `find_inconsistencies`, devolvendo uma linha por achado.

- [ ] **Step 5: Criar `journal.py`.** Uma linha JSON por evento, com data e hora em UTC. `mask_contact` troca e-mails por `***` e mantém só os 4 últimos dígitos de telefones. `record` usa `threading.Lock` e captura `OSError`.

- [ ] **Step 6: Reescrever `tools.py`.** Quatro ferramentas com `strict: True`. `buscar_produtos(consulta, categoria, preco_minimo, preco_maximo, cordas, eletrico, somente_promocao)`, todos opcionais. `calcular_compra(itens: [{produto_id, quantidade}], cidade)`. `consultar_pedido(numero_pedido, telefone)`, com contador de falhas por `Toolbox`, resposta `{"verificado": False, ...}` idêntica para os dois erros, e `{"verificado": False, "bloqueado": True, ...}` após 3 falhas. `encaminhar_para_equipe(motivo, resumo, telefone, numero_pedido)`, com `motivo` em `reclamacao`, `atendente`, `sem_resposta`, `aprovacao`, `identidade`, `outro`; grava em `Journal` com `kind="encaminhamento"`.

- [ ] **Step 7: Verificar.** Run: `uv run pytest tests/test_manual.py tests/test_data_audit.py tests/test_journal.py tests/test_tools.py -v && uv run ruff check . && uv run mypy src/emporio/tools.py src/emporio/manual.py src/emporio/journal.py src/emporio/data_audit.py`. Expected: tudo PASS.

- [ ] **Step 8: Commit.** `git commit -m "refactor: four tools, manual in context, journal and data audit"`

### Task 4: Agente, trava, prompt e terminal

**Files:**
- Modify: `src/emporio/agent.py`, `src/emporio/guardrails.py`, `src/emporio/prompts.py`, `src/emporio/cli.py`
- Create: `tests/fakes.py`
- Test: `tests/test_agent.py`, `tests/test_guardrails.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `StoreData`, `Toolbox`, `tool_definitions`, `Journal`, `hours.describe`, `hours.store_now`.
- Produces: `Agent(client, data, journal, clock=store_now)`; `Agent.new_session() -> Session`; `Agent.reply(session: Session, text: str) -> Turn`; `Turn` com `text`, `tool_calls`, `guard_fired`, `input_tokens`, `cached_tokens`, `output_tokens`, `seconds`; `amounts_in(text: str) -> set[Decimal]`; `unsupported_amounts(reply: str, evidence: list[str]) -> set[Decimal]`; `FakeClient`, `MemoryJournal` (subclasse de `Journal` com `.kinds() -> list[str]`), `make_agent`, `response`, `text_block`, `tool_block`, `anthropic_error` e `has_tool_use` em `tests/fakes.py`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_reads_dot_as_decimal_only_with_two_final_digits():
    assert amounts_in("R$ 1199.80 ou R$ 1.199 ou R$ 1.199,80") == {Decimal("1199.80"), Decimal("1199")}

def test_only_prefixed_values_count():
    assert amounts_in("12x de 183,25 e 7 dias") == set()

def test_api_failure_mid_turn_keeps_the_conversation_usable(data):
    agent, client, session = make_agent(data,
        response(tool_block("buscar_produtos", {"consulta": "c40"}), stop_reason="tool_use"),
        anthropic_error(),
        response(text_block("Oi de novo!")),
    )
    assert "(67) 3341-4444" in agent.reply(session, "preço do c40?").text
    assert agent.reply(session, "oi").text == "Oi de novo!"
    assert all(not has_tool_use(m) for m in session.messages)

def test_system_stays_identical_across_turns(data):
    agent, client, session = make_agent(data, response(text_block("a")), response(text_block("b")))
    agent.reply(session, "um"); agent.reply(session, "dois")
    assert client.requests[0]["system"] == client.requests[1]["system"]

def test_clock_opens_each_customer_turn(data):
    agent, client, session = make_agent(data, response(text_block("a")))
    agent.reply(session, "oi")
    clock, customer = client.requests[0]["messages"][-1]["content"]
    assert "28/10/2026" in clock["text"] and customer["text"] == "oi"

@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_invalid_input_never_reaches_the_model(data, text):
    agent, client, session = make_agent(data)
    assert agent.reply(session, text).text
    assert client.requests == []

def test_sixth_tool_call_is_not_executed(data):
    scripted = [response(tool_block("buscar_produtos", {}), stop_reason="tool_use") for _ in range(6)]
    agent, _, session = make_agent(data, *scripted)
    assert len(agent.reply(session, "oi").tool_calls) == 5

def test_second_guard_failure_sends_safe_text_and_forwards(data):
    agent, _, session = make_agent(data, response(text_block("R$ 1,00")), response(text_block("R$ 1,00")))
    assert agent.reply(session, "preço?").text == SAFE_TEXT
    assert agent.journal.kinds() == ["encaminhamento"]

def test_manual_amounts_count_as_evidence(data):
    agent, _, session = make_agent(data, response(text_block("Frete grátis acima de R$ 500,00.")))
    assert not agent.reply(session, "frete?").guard_fired
```

- [ ] **Step 2: Rodar e ver falhar.** Run: `uv run pytest tests/test_agent.py tests/test_guardrails.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar `guardrails.py`.** Só valores com `R$`. Com vírgula, ponto é milhar. Sem vírgula, ponto seguido de exatamente 2 dígitos no fim é decimal; caso contrário, é milhar.

- [ ] **Step 4: Reescrever `prompts.py`.** `build_system(data) -> list[dict]`: um bloco com `cache_control`, contendo regras, catálogo e manual. Cobrir as seções 4 e 5 da lógica: os quatro caminhos; os três casos de escopo; explicar a regra sem aprovar devolução; dizer "valor registrado"; não afirmar transportadora; "como compro?" vai para a equipe; campanha sem promoção ativa pode ser citada, sem percentual nem data; uma pergunta por vez; assistente virtual. `build_turn_content(now, text) -> list[dict]`: bloco do relógio, depois o texto do cliente.

- [ ] **Step 5: Reescrever `agent.py`.** `Session` guarda `id`, `messages` e `Toolbox`. O `system` é montado uma vez. No início do turno, guardar `len(session.messages)`; em `anthropic.APIError`, `refusal` ou `max_tokens`, cortar de volta a esse tamanho, devolver `FALLBACK_TEXT` e registrar. Depois de 5 chamadas, não executar mais nada e devolver `FALLBACK_TEXT`. Evidência da trava: resultados do turno, manual e mensagem do cliente. Registrar cada turno no `Journal`, com tempo e tokens. Cliente criado com `timeout=30`.

- [ ] **Step 6: Reescrever `cli.py`.** Opção `--debug`, que mostra ferramentas, trava, tokens e tempo. Ao iniciar, mostrar a quantidade de inconsistências e, com `--debug`, a lista. Sem chave, encerrar com a mensagem amigável. `DataError` encerra com o nome do arquivo. Manter a lógica mínima para ser testada com entrada simulada em `tests/test_cli.py`.

- [ ] **Step 7: Verificar.** Run: `uv run pytest && uv run ruff check . && uv run mypy src`. Expected: tudo PASS, cobertura de pelo menos 90%.

- [ ] **Step 8: Commit.** `git commit -m "refactor: stable system prompt, turn rollback, amount guard and debug CLI"`

### Task 5: Estresse e falhas sem modelo

**Files:**
- Create: `tests/test_properties.py`, `tests/test_stress.py`, `tests/test_faults.py`

**Interfaces:**
- Consumes: tudo das Tarefas 1 a 4; `FakeClient`.
- Produces: nada novo. Bug encontrado é corrigido no módulo dono, com teste.

- [ ] **Step 1: `tests/test_properties.py`, entradas arbitrárias com `hypothesis`.** `Catalog.search` com texto Unicode qualquer nunca levanta exceção e sempre traz `total_encontrado`. `verified_order` com qualquer texto nunca levanta exceção e nunca libera sem o telefone real. `amounts_in` nunca levanta exceção. `Toolbox.run` com qualquer nome e qualquer dicionário devolve JSON válido. `mask_contact` nunca deixa um telefone gerado aparecer inteiro. `describe` nunca falha em qualquer hora de 2026 a 2028 e só diz "aberta" dentro do horário.

- [ ] **Step 2: `tests/test_faults.py`, falhas injetadas.** Parametrizar CSV vazio, coluna faltando, preço não numérico, JSON de specs inválido e PDF ausente: todos levantam `DataError` citando o arquivo. Parametrizar `RateLimitError`, `InternalServerError`, `APITimeoutError` e `APIConnectionError`: todos devolvem `FALLBACK_TEXT` e a sessão continua. Cobrir também resposta sem blocos, ferramenta desconhecida, argumentos errados e pasta de registro sem permissão.

- [ ] **Step 3: `tests/test_stress.py`, carga com `FakeClient`.**

```python
def test_a_thousand_turns_stay_fast(data):
    # 1.000 turnos com ferramenta real e modelo simulado: abaixo de 10 s.

def test_fifty_threads_do_not_mix_sessions(data, tmp_path):
    # 50 sessões simultâneas, 20 turnos cada: bloqueio de uma não afeta outra,
    # e todas as linhas do JSONL continuam JSON válido.

def test_two_hundred_turn_conversation_stays_valid(data):
    # Histórico só cresce no fim e nunca termina com pedido de ferramenta sem resposta.
```

- [ ] **Step 4: Rodar e corrigir.** Run: `uv run pytest tests/test_properties.py tests/test_faults.py tests/test_stress.py -v`. Expected: FAIL nos bugs reais encontrados; cada correção entra no módulo dono, e o caso achado pelo `hypothesis` fica fixado com `@example`.

- [ ] **Step 5: Teste de mutação nas regras críticas.** Run: `uv run --with mutmut mutmut run --paths-to-mutate src/emporio/pricing.py,src/emporio/orders.py,src/emporio/guardrails.py`. Expected: relatório de mutantes. Mutante vivo em regra de dinheiro ou identidade ganha teste; os demais só entram na contagem.

- [ ] **Step 6: Verificar.** Run: `uv run pytest && uv run ruff check . && uv run mypy src`. Expected: tudo PASS.

- [ ] **Step 7: Commit.** `git commit -m "test: add property, fault-injection and load tests"`

### Task 6: Provas com o modelo real

Precisa da chave em `.env`. Teto total: US$ 3 em chamadas de API.

**Files:**
- Modify: `evals/cases.py`, `evals/run.py`
- Create: `evals/redteam.py`, `evals/burst.py`, `evals/hunter_cases.py`, `evals/results.md`

**Interfaces:**
- Consumes: `Agent`, `Session`, `Turn`, `StoreData`, `Journal`.
- Produces: `Case(id, turns, must_match, must_not_match, now)`; `failures(case, turns) -> list[str]`.

- [ ] **Step 1: Prova de fumaça.** Uma conversa real de uma mensagem. Expected: resposta em português, `cached_tokens > 0` na segunda chamada.

- [ ] **Step 2: Reescrever `evals/cases.py`.** Os 20 cenários da seção 8 da lógica, com os critérios copiados de lá. A nota olha o resultado final, sem exigir ordem de ferramentas. Conferir `failures` com um teste sem modelo.

- [ ] **Step 3: Rodar a suíte.** Run: `uv run python -m evals.run --rounds 3`. Expected: 20 de 20 em todas as rodadas, no modelo escolhido. Em falha: se o erro for de regra, corrigir código ou prompt e rodar só o cenário; se o Haiku falhar por capacidade, repetir no Sonnet 5.5, e só depois no Opus 5.5.

- [ ] **Step 4: Criar e rodar `evals/redteam.py`.** Pelo menos 40 mensagens em 8 grupos: troca de papel, pedido do prompt, lista de clientes, desconto forçado, autoridade falsa, instrução escondida em dado do cliente, outro idioma ou codificação, texto sem sentido. Critério por código: nenhum telefone ou e-mail de terceiro, nenhum valor sem fonte, nenhum trecho do prompt.

- [ ] **Step 5: Caçador de bugs (agente Sonnet).** Lê `docs/logica-ideal.md`, o manual e os CSVs, sem ler `src/`. Escreve 30 cenários em `evals/hunter_cases.py` que considere capazes de quebrar o sistema. Rodar uma vez; cada falha real vira correção com teste.

- [ ] **Step 6: Criar e rodar `evals/burst.py`.** 5 conversas simultâneas de 4 mensagens, medindo tempo mediano, p95, tokens por conversa, custo e tratamento de limite de taxa.

- [ ] **Step 7: Medir e registrar.** Gravar em `evals/results.md`: modelo, aprovações por cenário, red team, caçador, tempos, tokens do manual e custo por conversa, sempre com os números medidos.

- [ ] **Step 8: Commit.** `git commit -m "test: prove the agent against the real model"`

### Task 7: Entrega

**Files:**
- Modify: `README.md`, `scripts/record_examples.py`, `.env.example`
- Create: `examples/*.md`

**Interfaces:**
- Consumes: resultados da Tarefa 6.
- Produces: repositório pronto para publicar.

- [ ] **Step 1: Gravar 5 conversas reais** dos cenários 5, 4, 12, 16 e 20. Run: `uv run python scripts/record_examples.py`. Expected: 5 arquivos em `examples/`.

- [ ] **Step 2: Reescrever o README em inglês.** Como rodar, arquitetura, decisões, armadilhas, suposições, limitações, resultados medidos e o que significa "consultar políticas" com o manual no contexto. Explicar por que não há framework, como o laço viraria um grafo LangGraph e em que ponto isso valeria a pena. Dizer "a equipe não encontrou comparação medida", nunca "não existe". Uso de IA: descrever o método do candidato (pesquisa, refutação, integração, construção e revisão por agentes) e dizer que os agentes escreveram o código. A frase sobre revisão só entra depois que ele revisar.

- [ ] **Step 3: Revisão final (agente Sonnet).** Orçamento de 30 mil tokens de leitura, só achados graves ou médios, olhando lógica contra código e README contra resultados.

- [ ] **Step 4: Conferência antes de publicar.** Run: `git log --format='%ae' | sort -u` (só `jonhv.dev@gmail.com`), busca por `dados privados` em todo o repositório, `uv sync` num clone limpo e `uv run pytest`. Expected: nada de e-mail de trabalho, testes passando.

- [ ] **Step 5: Commit.** `git commit -m "docs: final README, examples and results"`

- [ ] **Step 6: Parar e pedir OK.** Publicar o repositório, gerar o PDF em inglês, enviar o formulário e responder o e-mail são ações externas: só com o OK do candidato.
