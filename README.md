# Hope Today — a good-news agent

> **"How can I show you there is hope today?"**

An AI agent that asks you that one question, figures out what would genuinely give *you* hope, scans today's news for real, substantive good news on those things, and hands it back as a short, fun slide deck.

This is a from-scratch learning project: the agent loop, the harness around it, and the MCP tool servers are all hand-built — no agent frameworks — to understand how agentic systems actually work.

---

## How it works

1. **Ask.** The agent opens with *"How can I show you there is hope today?"*
2. **Interpret.** It turns the answer into search topics. The answer might be:
   - a topic ("space stuff") → search it directly
   - a worry ("climate feels hopeless") → look for counter-evidence and real progress
   - a feeling ("rough week") → broadly uplifting, lighter stories
   - nothing ("surprise me") → saved interests plus a wildcard topic
   It may ask **one** short follow-up if the answer is too vague, then commits.
3. **Research.** It searches today's news and opens the promising articles, within a fixed budget.
4. **Judge.** It keeps only stories that are genuinely positive, significant and credible, and drops fluff and spin.
5. **Present.** It builds a 5–7 slide HTML deck, one story per slide: headline, what happened, why it matters (tied back to what you said), and a source link.

---

## Architecture

```
Web app (later)
      │
Agent harness ── the loop, guardrails, budgets, tracing
      │
      ├── Model adapter   → OpenAI API now, open models (Ollama / vLLM) later
      ├── News MCP server → search_news, fetch_article
      ├── Deck MCP server → render_deck
      └── Storage         → preferences, seen stories, cache
```

### Design decisions

| Decision | Choice | Why |
|---|---|---|
| Agent style | **Full agent**: one loop, the model decides the steps | Keeps orchestration simple, so the focus stays on MCP tool design and the harness |
| Model | **OpenAI API first** (`gpt-4o-mini`), open-source later | Build on a stable model; swap behind an adapter once evals exist |
| Model interface | Single `chat(messages, tools)` adapter | Changing models touches one file |
| Tools | Exposed via **MCP servers** | Tools are reusable by any MCP client (this harness, Claude Desktop, etc.) |
| Sources | The Guardian Open Platform + RSS (free) | Full article text, no cost; paid APIs only if coverage is thin |
| Framework | None | The point is to learn what frameworks hide |

---

## MCP servers

### `news` server
| Tool | Purpose |
|---|---|
| `search_news(query, since)` | Recent headlines, URLs and snippets for a topic |
| `fetch_article(url)` | Cleaned, truncated article text |

### `deck` server
| Tool | Purpose |
|---|---|
| `render_deck(title, user_answer, stories[])` | Validates stories and renders an HTML slide deck |

---

## Harness responsibilities

With a full agent the model is in charge, so the harness is what keeps it on the rails:

- **Safety gate.** Before the loop starts, check the user's answer for real distress. If found, respond with care and point to support (e.g. Samaritans of Singapore, 1767) instead of generating slides.
- **Budgets.** Cap loop turns and articles fetched. When the cap is hit, tell the model to wrap up rather than killing the run.
- **Stopping rule.** A run only succeeds if `render_deck` was called; otherwise nudge once, then fail cleanly.
- **Validation as feedback.** Tool errors (bad input, missing sources) go back to the model as readable messages so it can self-correct.
- **Context management.** Truncate or summarise long tool results before they re-enter the conversation.
- **Untrusted input.** Article text is data, never instructions; defend against prompt injection in fetched content.
- **Tracing.** Log every model call, tool call and result for debugging.

---

## Roadmap

| Phase | Build | Done when |
|---|---|---|
| **1. Foundations** | Setup, chat loop, fake `search_news` tool, agent loop | The model calls a fake tool and answers from it |
| **2. Real pipeline** | Guardian + RSS search, article fetch, judging, HTML deck | One CLI command produces today's deck |
| **3. MCP** | Move tools into the `news` and `deck` servers; harness becomes an MCP client | Same deck, plus Claude Desktop can use the servers |
| **4. Quality** | Eval set, seen-story memory, cache, prompt-injection tests | Changes can be measured, not guessed |
| **5. Open models** | Point the adapter at Ollama; compare against evals | Know which open model is good enough, and where the harness must compensate |
| **6. Ship** | FastAPI backend, web page, Docker Compose, daily schedule | A fresh deck is live at a URL every morning |

---

## Evals (Phase 4)

- **Planner:** ~20 sample answers to the opening question; check that the chosen topics make sense.
- **Judge:** ~50 hand-labelled headlines (`hopeful` / `fluff` / `not positive`); measure agreement.
- **Safety:** sample answers ranging from "meh" to real distress; check the gate triggers correctly.
- **Injection:** a planted article containing "ignore your instructions"; the agent must not comply.

---

## Planned structure

```
hope-today/
├── harness/
│   ├── agent.py        # the agent loop
│   ├── llm.py          # model adapter: chat(messages, tools)
│   ├── mcp_client.py   # connects to MCP servers, lists and calls tools
│   ├── guards.py       # safety gate, budgets, stopping rules
│   └── tracing.py      # run logs
├── servers/
│   ├── news_server.py  # MCP: search_news, fetch_article
│   └── deck_server.py  # MCP: render_deck
├── templates/
│   └── deck.html       # slide template
├── evals/
├── .env.example        # OPENAI_API_KEY, GUARDIAN_API_KEY
└── README.md
```

---

## Stack

Python 3.11+ · `openai` SDK · official `mcp` Python SDK · `requests` / `feedparser` · `pydantic` · Jinja2 · later FastAPI, Docker, Ollama

---

## Status

🟡 **Phase 1: Foundations**, starting now.
