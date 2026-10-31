# Empório da Música: customer-service agent

Text-message agent for a fictional musical instrument store in Campo Grande/MS. "Tom" answers
customers in Brazilian Portuguese, looks up products, promotions and orders in the store's data,
applies the rules of its policy manual, and hands off to the team when it should.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and an [Anthropic API key](https://console.anthropic.com).

```bash
uv sync
cp .env.example .env          # then fill in ANTHROPIC_API_KEY
uv run emporio --trace        # chat in the terminal; --trace shows each tool call
```

Resume a conversation with `uv run emporio --session <id>`. Everything else needs no key:

```bash
uv run pytest                 # unit tests, model replaced by a scripted fake
uv run python scripts/audit_data.py   # contradictions found in the data
```

With a key, `uv run python -m evals.run` runs the scenarios against the real model and
`uv run python scripts/record_examples.py` regenerates `examples/`. Set `EMPORIO_MODEL` and
`EMPORIO_EFFORT` to change the model or effort, and `EMPORIO_NOW` to pin the clock.

## How it works

```
customer message
      │
      ▼
agent loop (src/emporio/agent.py)
      │  sends: system prompt, clock, last 20 messages, tool definitions
      ▼
Claude ──asks for a tool──► Python tool ──► CSVs, manual sections, SQLite
      ▲                          │
      └──────── JSON result ─────┘
      │
      ▼ final text
amount check: every R$ value must come from this turn's tools or from the customer
      │
      ▼
reply, saved as plain text in SQLite
```

| Tool | Purpose |
|---|---|
| `search_products` | Catalog search with price and spec filters; returns availability, price, PIX and installments |
| `list_promotions` | Active promotions; tells when a campaign the customer cites has ended |
| `quote_order` | Totals for several items: PIX, installments, shipping |
| `get_order` | Order status, after an identity check |
| `check_return` | Return, exchange and warranty decision with exact date arithmetic |
| `read_policy` | Reads manual sections by number |
| `open_ticket` | Registers a case for the human team and returns a protocol |

## Technical decisions

**Approach: function calling with narrow, typed tools, without a framework.** Questions about prices,
stock and orders have one exact answer, so they should be queries, not semantic search. I ruled out a
text-to-SQL agent because the database holds customer phones and e-mails: with typed tools, a prompt
injection has nothing to reach, since no tool can list customers. I also left out LangChain and similar
frameworks. The loop in `agent.py` is short, and in an agent this small it is easier to read and test
directly.

**Model: Claude through the official SDK.** It supports strict tool schemas, and prompt caching makes
the fixed system prompt cheap across turns. The default is `claude-opus-5-5` at low effort; the model
is one environment variable. The tools know nothing about the provider, so changing vendor means
changing the client in `agent.py`.

**Retrieval: section lookup, without embeddings.** The manual is small and already structured (28
numbered sections, about 11,000 characters). The system prompt carries the table of contents and the
model asks for sections by number. Sections stay whole, including tables and text that crosses pages,
and every answer can be traced to the section read. Embeddings would add a dependency and chunking
problems without improving recall at this size. With many or unstructured documents I would move to
hybrid search.

**Prompt strategy: the model talks, Python decides.** The prompt defines the persona and when to use
each tool. Discounts, installment limits, shipping and return windows are computed in Python, so the
model never does arithmetic or counts days. The prompt is split in two blocks: the stable part is
cached, and the clock sits outside it so it does not invalidate the cache.

**Conversation history: SQLite, last 20 messages, text only.** A customer on a messaging channel
returns hours later, so persistence helps. Tool results are deliberately not kept: prices and stock
change, so each turn fetches facts again. This also enforces the manual's rule of never quoting
without checking the system.

**Safety in code, not only in the prompt.**
- Amount check: if a reply has an R$ value that did not come from this turn's tools or the customer,
  it goes back to the model once, and is then replaced by an offer to confirm with the team.
- Order data requires the order number plus the phone or e-mail on file. A wrong contact and a missing
  order get the same answer, and three failures lock the session.
- Tool results carry the customer's first name only, never contact data.
- A model refusal or a runaway loop becomes a message pointing to the store's phone.

**Interface: terminal.** The brief asks for the agent working correctly, and a CLI keeps the focus there.

**Opening hours** use the `America/Campo_Grande` time zone (one hour behind Brasília) and Brazilian
national and Mato Grosso do Sul holidays, so on Sunday, November 1, 2026 the agent knows the store
reopens on Tuesday, after Finados.

## Data problems found and how the agent handles them

`scripts/audit_data.py` reproduces these findings.

| Finding | Decision |
|---|---|
| Item 136 is discontinued with 13 in stock; item 130 is `coming_soon` with 2 in stock | Status wins: neither is offered and no price is shown |
| Item 96 is active with zero stock | Reported as temporarily unavailable, with alternatives |
| 7 descriptions name another brand (a "Music Man Bass" described as a Fender Jazz Bass) | Name and specs win; those descriptions are hidden and not searched |
| Sopro and Cordas Orquestrais categories have no products, though the manual lists them | Agent says there are none today |
| Manual claims 300+ instruments; the catalog has 65 | Agent does not repeat the claim |
| Promotions have no dates, and some products have several expired rows | `is_active` is the only signal |
| Orders 3 and 20 have totals that differ from their items | The recorded total is what the customer paid; nothing is recomputed |
| Five PIX orders show no 5% discount; orders 9, 16 and 18 exceed the installment limits | Historical records, reported here for the store to review |
| Orders 3 and 14 contain an item that is `coming_soon` | Order data is shown as recorded |
| Two customer records share an e-mail, and similar names exist | Name never identifies a customer |
| Data stops in March 2026 | Orders from then look stalled or late under the real clock; the agent says so and offers a ticket |

## Assumptions

The brief asks to assume, document and move on. The store should confirm these. Each one is attached
to its manual section in `src/emporio/policies.py`.

| Topic | Manual says | Assumption |
|---|---|---|
| Phone | (67) 3341-4444 in 1.2, (67) 3321-4500 in 7 | Use 3341-4444 |
| E-mail | Spelled with and without an accent | Use `contato@emporiodamusica.com.br` |
| Installments | Table: minimum R$ 100. Section 3.1: tiers | 3.1 is more specific and prevails |
| Up to 3x | "No minimum (except below R$ 50)" | Installment cannot be below R$ 50 |
| Defect, day 31 to 90 | 4.2 sends the customer to the manufacturer; 8.1 gives 90 days of legal warranty | Do not deny; forward to the team |
| Return window | Counts from receipt, but there is no delivery date in the data | Use the estimated delivery date |
| Online purchase | 4.1 is for online sales only; orders have no channel | Treat shipped orders as online |
| Preference exchange | 7 days, no start date | Count from receipt |
| Cancelling before shipping | Not covered | Open a ticket |
| Shipping at exactly R$ 500 | "Above" and "below" R$ 500 | Free |
| Metro region | Not defined | Only Campo Grande is confirmed |
| "Desconto Exclusivo" | Audience not stated | Applies to any customer while active |
| Partner stores | "Suggest when possible"; none listed | Never name a store |

## Evaluation

`evals/cases.py` holds scenarios that each pin one manual rule or data trap, checked with deterministic
assertions on tools called and on the text of the answer. Latest run: [`evals/results.md`](evals/results.md).

## Known limitations

- Data is read from CSV at startup. Stock changes need a restart, and nothing reserves stock or places orders.
- Order number plus phone is a weak identity check. On WhatsApp the verified sender number should replace it.
- The amount check covers money only. It does not verify dates or product names, and misses amounts written in words.
- Municipal holidays are missing from the opening-hours logic.
- Chat history has no expiry. A data-deletion request opens a ticket instead of deleting anything.
- No tool answers shipping costs outside Campo Grande, because the data has no carrier rates.

## With more time

- Connect a WhatsApp webhook and a real database, with the sender's number as verified identity.
- Build the team's inbox for tickets and let an attendant take over a conversation.
- Grow the eval set from real conversations and run it in CI.
- Add tracing and cost metrics per conversation.
- Add automatic expiry and deletion of personal data.

## Use of AI coding assistants

I used **Claude Code** (model Claude Opus 5.5) as the main tool, and it wrote most of this repository.
Every commit it took part in has a `Co-Authored-By` line.

Workflow:
1. Claude Code read the brief, the manual and all CSVs and listed the contradictions before any code.
2. It proposed the architecture and wrote the modules with their tests, in small commits.
3. Tests and real runs corrected the work along the way. A test caught a one-cent PIX rounding error
   on orders with quantity above one, and checking the extracted text showed the PDF library's default
   mode returned one word per line.

My part was setting the goal and constraints, reviewing the decisions and the result, and running the project.

## Repository

```
src/emporio/   agent.py (loop), tools.py, catalog.py, orders.py, pricing.py,
               policies.py, hours.py, guardrails.py, prompts.py, store.py, cli.py
tests/         unit tests, no API key needed
evals/         scenarios for the real model and latest results
examples/      recorded conversations
scripts/       data audit and example recorder
data/          store data as provided (fictional)
```
