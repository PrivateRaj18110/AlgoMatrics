# AI platform (Phase 13)

A trading assistant plus domain explanations (strategy, risk, logs, analytics,
broker diagnostics), built on Claude through a pluggable provider. Gated by the
`ai` feature flag (Phase 4).

## Architecture

`modules/ai` follows Clean Architecture:

- **Port** (`application/ports.py`) — `LLMProvider.complete(system, messages)`.
- **Providers** (`infrastructure/`):
  - `AnthropicProvider` — the official async Anthropic SDK, model
    `claude-opus-4-8` with adaptive thinking. The client is created lazily so the
    optional `anthropic` extra is only needed when selected.
  - `NullProvider` — the default; never makes a network call and returns a clear
    "AI is not configured" message. Keeps the feature safe out of the box and the
    tests hermetic.
- **Prompts** (`domain/prompts.py`) — pure `(system, user)` builders. The system
  prompt scopes the assistant to the trading domain and **forbids fabricated
  numbers** ("only use figures present in the provided context").
- **Service** (`application/service.py`) — assembles prompts and calls the
  provider.

## Configuration

```
AI_PROVIDER=null          # or "anthropic"
ANTHROPIC_API_KEY=...     # required when AI_PROVIDER=anthropic
AI_MODEL=claude-opus-4-8
AI_MAX_TOKENS=2048
```

Selecting `anthropic` without a key safely falls back to the null provider.
Install the extra: `uv sync --extra ai` / `pip install '.[ai]'`.

## API (`/api/v1/ai`, feature-gated)

| Method & path | Purpose |
|---|---|
| `GET /prompt-templates` | Available assistant capabilities |
| `POST /assistant` | Free-form question (optional `context`) |
| `POST /explain-strategy` | Explain a strategy (`{context}`) |
| `POST /explain-risk` | Explain a risk configuration |
| `POST /analyze-logs` | Analyze log lines |
| `POST /analytics` | Natural-language analytics over metrics |
| `POST /broker-diagnostics` | Diagnose a broker connection |

Endpoints receive the domain object the caller already holds (the frontend
already loaded the strategy, risk, metrics, or broker status), which keeps the AI
module decoupled from every other context.

## Frontend

`/app/assistant` (nav entry shown only when the `ai` flag is enabled) sends a
question and renders the answer, flagging when the null provider is active.

## Safety

- The assistant **explains and advises; it never trades or changes settings.**
- The system prompt forbids invented figures.
- The whole surface is behind the `ai` feature flag and is off unless enabled.

## Rollback

- **Runtime:** turn off the `ai` flag (API denies, nav entry disappears), or set
  `AI_PROVIDER=null`.
- **Code:** isolated to the `phase-13-ai` branch; no schema change, so
  `git revert` is safe.
