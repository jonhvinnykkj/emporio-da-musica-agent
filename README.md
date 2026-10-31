# Empório da Música: customer-service agent

"Tom" is a text-message agent for a fictional musical instrument store in Campo Grande/MS. It answers in Brazilian Portuguese, reads prices, stock, promotions and orders from the store's CSV files, applies the policy manual, and hands off to the team when it should.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and an [Anthropic API key](https://console.anthropic.com).

```bash
uv sync
cp .env.example .env                  # then set ANTHROPIC_API_KEY
uv run emporio --debug                # chat in the terminal; --debug shows tools, guard, tokens, time
uv run pytest --cov=src/emporio       # no key needed: the model is replaced by a scripted fake
```

Optional variables in `.env`: `EMPORIO_MODEL` (default `claude-haiku-5-5`), `EMPORIO_EFFORT` (default `medium`) and `EMPORIO_NOW`, which pins the store clock (for example `2026-10-31T14:00:00`).

The proofs with the real model need a key. They read only this project's `.env`, stop on a missing key, and stop when the spending cap (`--budget`, in US$) is reached. Each suite writes its own file in `evals/results/`.

```bash
uv run python -m evals.run --rounds 3                  # 21 scenarios, graded by code
uv run python -m evals.run --suite cacador --rounds 3  # extra scenarios aimed at the weak spots
uv run python -m evals.redteam                         # hostile messages
uv run python -m evals.burst                           # five simultaneous conversations
uv run python -m scripts.record_examples               # regenerates examples/
```

## How it works

One message goes through these steps:

1. The code drops empty input and input over 2,000 characters.
2. The code puts the clock (date, time in `America/Campo_Grande`, open or closed, next opening) at the start of the customer's message.
3. The model answers, asks for a missing detail, calls a tool, or declines.
4. The code validates the tool arguments, runs the tool and returns JSON. After 5 tool calls in a turn, the model must answer with what it has.
5. The model writes the answer from the returned fields.
6. The code checks every amount written as `R$`. An amount that is not in this turn's tool results, in the manual or in the customer's message goes back to the model once. If it fails again, the customer gets a fixed safe reply and the case is forwarded.
7. The code logs the exchange to JSONL with phone numbers masked.

If the API or a tool fails, the turn is rolled back, so the history never holds a tool request without its answer. The customer gets a fixed message with the store's phone and WhatsApp.

| Tool | What it does |
|---|---|
| `buscar_produtos` | Catalog search by text, category and price. Returns availability, price, PIX and installments already computed. Shows 5 items, up to 15 on request, and states the total. |
| `calcular_compra` | Quantity or several products: subtotal, PIX total, installments and shipping (Campo Grande only). |
| `consultar_pedido` | Order status. Needs the order number and the phone on file. |
| `encaminhar_para_equipe` | Writes a handoff to a file. It changes no store data. |

## Technical decisions

**Single agent.** The case is small: 65 products, 20 orders, one short manual. Nothing runs in parallel and nothing overflows the context. One message often mixes data and policy ("how much is the C40, and can I exchange it?"). Discarded: a supervisor with specialists, and a router that only unlocks tools. Both add hops for the same message. We found no measured comparison between a single agent and a multi-agent design for customer service. This is an engineering argument, not a measurement.

**Provider SDK directly, no framework.** The whole of `src/emporio/agent.py` is about 200 lines. Discarded: LangGraph and LangChain. This loop is already a graph with three nodes: model, tools, and the check on amounts, with an edge back from the check to the model and another from the model to the tools. LangGraph would draw the same graph and add a dependency. It would pay off if there were branches that run in parallel, state that must survive a restart, a human approval step in the middle of a run, or several agents. None of these exists here.

**Model: the smallest one that passes the proofs.** The default is Haiku 5.5 at medium effort. The test order was Haiku 5.5, Sonnet 5.5, Opus 5.5, so the choice comes from the proofs, not from preference. On the three hardest scenarios, 10 rounds each, Haiku at low effort passed 29 of 30, Haiku at medium 30 of 30, and Sonnet at low 21 of 30, at 16 times the cost. More effort helped and a larger model did not. Opus was not run, because Haiku had already passed. Both settings are environment variables.

**The whole manual in the context.** The manual has 8 pages and about 1,750 words. "Consult policies" means that the model reads the manual that is in its fixed context and the manual wins over the model's own knowledge. There is no policy tool, no RAG and no embeddings. Discarded: retrieval, which could bring the wrong section back, and a policy tool, which adds a call for text that already fits. At a much larger manual, search by keywords comes first, then embeddings.

**Code decides, the model talks.** Price, PIX, installments, shipping, availability, active promotion, clock, identity and limits are computed in Python. The model picks tools and writes the reply. Discarded: letting the model compute from the manual, and a text-to-SQL agent. A SQL agent would keep the business rules in the prompt and leave no clear trace.

**The clock goes inside the customer's message.** The system prompt never changes during a conversation. Changing it between turns would invalidate the cache and the reasoning blocks that are sent back with the history. Discarded: a clock line in `system`.

**Persistence: memory plus a JSONL log.** The history lives in memory for the session. The log keeps messages and handoffs with masked contact data. Discarded: a database, and resuming conversations across runs. For a terminal tool, resuming is not worth keeping more personal data.

**Interface: terminal.** `--debug` shows the tools called. A web UI would cost more and would not change how the logic is judged.

## Customer-service rules

Where a rule comes from the manual, the section is cited. Evidence for the rest is design judgement.

| Rule | Origin |
|---|---|
| Never state price, stock, deadline or status without a lookup | Manual 7.1 and 7.3 |
| Complete answer in one message, one question at a time. For an order, ask for identification first | Design principle. Manual section 9 for orders |
| Informal, warm tone, customer's name when known | Manual 7.1 and 7.2 |
| Complaint: acknowledge the problem, state the fact, forward. Do not mirror emotion or pretend to feel it | Manual 7.3. Design choice on the wording |
| The 24-business-hour return time applies to complaints only | Manual 7.3 |
| A path to a person is always open | Manual 7.3 and 10 |
| Introduce itself as a virtual assistant, never as a person | Manual section 7. Design choice |
| Outside opening hours, keep answering and say when the team returns | Manual 2 and 7.1 |
| Sold out or discontinued: say so and suggest an available alternative | Manual 7.3 |
| Expired promotion: say so and show the current price | Manual 7.3 |
| Promotional price always with original price and percentage | Manual 6.2 |

## Traps in the data and the manual

`emporio.data_audit.find_inconsistencies` finds the data problems at startup. `--debug` prints them.

**Manual**

| Trap | Decision |
|---|---|
| Phone 3341-4444 (cover and 1.2) against WhatsApp 3321-4500 (section 7) | Both, labelled by channel (D3) |
| E-mail with and without an accent | The one without an accent. Not proven to be the valid one |
| Installment table says R$ 100 minimum, section 3.1 gives tiers. 16 of 65 products change their maximum | Section 3.1 (D4) |
| 30 days from purchase (4.2) against 90 days from receipt (8.1) | Different periods. The agent cites both. A defect between day 30 and 90 goes to the team |
| 4.3 does not say when the 7 days of a preference exchange start | Cite as written. The team confirms |
| Manual says 300 instruments, the CSV has 65. Manual dated June 2025 | The system is the truth for what exists |
| Partner stores mentioned but not listed | None is named |
| Black Friday and Semana do Músico appear in the manual, with no active promotion in the CSV | The agent may say the campaigns exist. No percentage, no date |
| No online store link and no purchase path | "How do I buy?" goes to the team |

**Products and promotions**

| Trap | Decision |
|---|---|
| No product name contains "violão", "ukulele", "guitarra" or "baixo" | Search takes a category. Free text matches name and category |
| Categories 6, 7 and 8 have no products | The tool says "category without products". The agent never says "we don't sell" and offers to check with the team |
| Fuzzy search with no cut-off returned ukuleles for "saxofone" | Minimum similarity. Below it: not found |
| Six products name a brand in the description that differs from the name; two have specs that contradict the description | Name and price stand. The six, plus the discontinued 136, show no description or specs. Technical detail goes to the team |
| 136 is discontinued with 13 in stock | `available = status == "active" and stock > 0`. Status wins |
| 113 is discontinued with stock 0. 96 is active with stock 0 | Same rule |
| 130 is `coming_soon` with stock 2 and appears in two orders | Unavailable. No date promised. Past orders are not recalculated |
| 20 of 25 promotion rows are inactive, some for the same product | Only `is_active = 1` counts. The 4 active ones do not collide |
| The assignment's own example, the Takamine GD20, has an inactive 12% promotion | R$ 2,199.00, no discount |
| Ohana CK-20 with 20% falls to R$ 439.20, under the free-shipping line | Free shipping is judged on the final value (D6) |

**Orders and customers**

| Trap | Decision |
|---|---|
| Order 8 shipped, delivery estimate 245 days past | Report the record and the delay, offer to forward |
| Orders 9 to 16 pending or confirmed since February and March | `requer_atencao` computed in code (D7) |
| The manual does not define `pending` or `confirmed` | Show the translated status without explaining it |
| No tracking or estimate for pending, confirmed or cancelled orders | Say there is none yet. Invent nothing |
| Orders 3 and 20 have a total different from the sum of their items | Do not recalculate |
| In the 5 PIX orders the total equals the list price. No Campo Grande total under R$ 500 shows the R$ 35 shipping | Call it "recorded value", never "you paid". A dispute goes to the team |
| Orders 9, 16 and 18 break the minimum installment of 3.1 | History is not precedent |
| No field says whether a purchase was online, and 4.1 covers online purchases | Ask, or leave it to the team |
| Delivered orders in Campo Grande carry a BR code, while 5.1 speaks of motorcycle couriers | Pass the code, name no carrier |
| Customers 11 and 43 share an e-mail | E-mail identifies nobody. The phone is unique across the 50 customers |
| Order ids 1 to 20, easy to try in sequence | Phone required, 3 failures per session lock lookup |
| Saturday 31 October 2026, and Monday 2 November is a holiday (Finados) | National holidays in a list in the code (D8) |
| Prompt injection | No suspicious text found in the CSVs. Every tool result is still treated as data |

## Assumptions

| # | Decision |
|---|---|
| D2 | The clock is the real one, in `America/Campo_Grande`, and can be pinned for tests (`EMPORIO_NOW`). With the real date, orders from February and March look late. |
| D3 | Phone (67) 3341-4444 and WhatsApp (67) 3321-4500, because section 7 is the one about channels. |
| D4 | Installments follow section 3.1: up to 3x with a R$ 50 minimum, 4x to 6x with R$ 80, 7x to 12x with R$ 100. "Except below R$ 50" is read as the R$ 50 minimum installment up to 3x. |
| D5 | A check on `R$` amounts only. An amount written in words ("mil reais") escapes it. |
| D6 | Free shipping in Campo Grande from R$ 500 on the final value. Below that, R$ 35. Other cities never get a value. |
| D7 | `requer_atencao` is true for a shipped order with an overdue estimate, or pending or confirmed for more than 15 calendar days. The 15 is our choice, close to the longest standard shipping time. |
| D8 | National holidays in a list in the code, with Good Friday computed. Municipal and state holidays are not covered. |
| D9 | In-memory history plus a JSONL log. No conversation resume. |

Also decided: the return deadline is counted in code, since `consultar_pedido` returns the days since purchase and since the delivery estimate. Without a receipt date in the data, the estimate stands in for it, and the agent says so.

## Quality and evidence

Everything here was measured in this repository.

- **Tests:** 310, all passing. Coverage of `src/emporio` is 99.6% (`uv run pytest --cov=src/emporio`). CI also runs `ruff check` and `mypy src`.
- **Mutation testing:** 405 of 416 mutants killed in `pricing`, `orders` and `guardrails`. The 11 survivors are field mutants in `OrderBook` that a test does assert. The tool credits them to the one test that built a shared fixture, so it never reruns that test against them.
- **Property tests (hypothesis):** search, order verification, amount parsing, tool dispatch, phone masking and opening hours, on inputs nobody wrote by hand.
- **Injected faults:** broken store data, API errors before and after a tool call, a tool that raises, a response with no blocks, a journal that cannot be written.
- **Load with a simulated model:** 1,000 turns, 50 concurrent threads with separate sessions, and a 200-turn conversation. These use a scripted model and the real tools.
- **Two real bugs found by this stress work.** `Catalog.search` raised on a price limit that was not a number (hypothesis found `{"preco_minimo": []}`). `mask_contact` left a phone whole when it was glued to a word, such as `whatsapp67996547821`.

Real-model results, on `claude-haiku-5-5` at medium effort, on the code in this repository. Full tables are in `evals/results/`.

| Proof | Result |
|---|---|
| 21 scenarios, 5 rounds each | 105 of 105 rounds passed |
| 34 scenarios aimed at the weak spots, 5 rounds each | 166 of 170 rounds passed |
| 49 hostile messages | 47 passed. No customer data and no stretch of the rules came out |
| 5 simultaneous conversations, 20 answers | None fell back to the contingency text. Median 3.0 s, p95 7.7 s |

That final run cost about US$ 0.23. A four-message conversation costs about US$ 0.004, an estimate from the tokens used.

The misses, read by hand:

- Of the 4 missed rounds, 3 are correct answers in wording the regex does not accept, such as "já passamos do nosso horário". The fourth left out a tracking code. The regexes stayed as they are, because tuning them to a run proves nothing.
- Both failed hostile messages were refused. The agent gave the real answer but repeated the attacker's amount ("não consigo confirmar R$ 10,00"), which the rule forbids.

**What the real model found that a simulated model could not:**

- "Vocês têm ukulele concert?" came back wrong in 7 of 8 tries. The model set the filters, left the customer's words out of the search, repeated the same call and said the store had none, while 4 are in stock. No scenario caught it, because all of them named a model. The tool description, a new `limite` field and a rule at the tool cap fixed it, and four scenarios now pin it.
- On a Saturday, an answer offered the Monday holiday as the next opening. The clock now names the holiday.
- A return was flatly refused, and the 24-hour return time was left out of a complaint. The prompt now states both rules.

These runs also exposed scenario criteria that were too narrow. They were widened only for wording that was correct. An independent review then found that three had gone too far and let a wrong answer pass, and those were narrowed again. The commits record each change.

## Known limitations

- The CSVs are read at startup. Stock changes need a restart. Nothing reserves stock or places orders.
- Order number plus phone is a weak identity check. With WhatsApp, the sender's number would replace it.
- The `R$` check does not read amounts in words, dates, percentages or product names.
- Municipal and state holidays are missing.
- No shipping value outside Campo Grande, because the data has no carrier rates or ZIP-code table.
- The manual dates from June 2025 and mentions 300 instruments. The system covers the 65 that exist.
- History is not cut. A very long conversation grows the request.
- The log masks phones and e-mails. A name written in free text is not masked.
- Scenarios are graded by regex, so a correct answer in unexpected words can fail and a wrong one could pass. The misses still have to be read by hand.
- When refusing a made-up price, the agent sometimes repeats the amount. The real price is in the same answer.
- Search shows 15 items at most. Violões has 33 in stock, so the agent states the total and narrows the list.

## With more time

- A WhatsApp webhook, where the sender's number arrives verified.
- A real database and a team inbox, with an attendant taking over a conversation.
- A flow driven by code, with human approval, if the agent ever cancels or refunds.
- Search by keywords, then embeddings, if the manual grows.
- A grading set built from real conversations, run in CI.
- Tracing and cost per conversation.

## How this was built

AI wrote most of this repository. The method was set by the candidate:

1. One team of agents researched how to serve customers well. A second team tried to refute each claim. Of 27 claims, 7 were confirmed, 18 weakened and 2 refuted.
2. An integrator corrected the material. The candidate approved 14 decisions. They are in `docs/logica-ideal.md`, which is the logic this project follows.
3. Builder and reviewer agents then implemented the work task by task, following the plan in `docs/superpowers/plans/`. Agents wrote the code, the tests and this README, using Claude Code.

An earlier draft, written before the method existed, was rewritten from the new logic. The git history keeps it.

The assignment asks for an explanation of AI use, and this section is that explanation. Every commit written with Claude Code carries a `Co-Authored-By` line.

## Repository layout

```
src/emporio/   agent.py (loop), tools.py, catalog.py, orders.py, pricing.py, hours.py,
               guardrails.py, journal.py, manual.py, prompts.py, data_audit.py, cli.py
tests/         unit, property, fault-injection and load tests; no key needed
evals/         scenarios, hunter cases, red team and burst; results in evals/results/
examples/      recorded conversations (scenarios 5, 4, 12, 16, 20)
scripts/       record_examples.py
data/          store data and policy manual, as provided (fictional)
docs/          logica-ideal.md (the logic) and superpowers/plans/ (the build plan)
```
