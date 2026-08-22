# 08 — Tech Stack Decisions

Every choice with a justification and what we rejected. Constraint context: local-first, < 3,000 lines, < $550 AWS credits, Bedrock-only LLMs, single builder.

| Layer | Choice | Why | Rejected |
|-------|--------|-----|----------|
| Language (core) | **Python 3.12** | Ecosystem for graphs + ML eval + boto3; type hints mature | Node/TS (weaker graph/ML ecosystem for this) |
| API framework | **FastAPI** | Pydantic-native validation = the input contract *is* the schema; async; auto OpenAPI docs | Flask (manual validation), gRPC (overkill for demo) |
| Validation/models | **Pydantic v2** | Rust-fast, strict types, JSON-schema export for the audit trail | dataclasses (no validation) |
| Graph engine | **networkx** | In-process, GraphML persistence, enough for 1k–100k nodes; clean port/adapter to swap | Neo4j local (extra infra + lines), igraph (heavier) |
| Relational store | **SQLite + SQLAlchemy 2** | Zero-config, file-based, append-only triggers for audit; SQLAlchemy keeps the door open to Postgres | Postgres local (infra overhead, no benefit at this scale) |
| LLM inference | **boto3 → AWS Bedrock** (default credential chain) | Required constraint; models: Nova Lite (extraction), gpt-oss 120B w/ GLM-5 fallback (explanation) | LangChain/LangGraph wrapper — unnecessary abstraction for 2 direct Bedrock calls with constrained JSON output; fewer deps, fewer lines, more control. *Deliberate "where not to use a framework" decision* |
| LLM structured output | **Constrained JSON via Bedrock response format + jsonschema validation + 1 retry** | Deterministic pipeline beats agent-style parsing | LLM function-calling frameworks |
| Dashboard (P1) | **Single-page HTML + embedded mermaid.js/d3 graph, served by FastAPI** | Zero build toolchain, ~150 lines, shows the graph visually | Next.js app (build tooling not justified for a P1 analyst view; Prakhar knows Next.js and *chose* to skip it — simplicity-first) |
| Tests | **pytest + coverage** | Standard, fast, parameterized tests for feature/score cases | unittest (verbose) |
| Lint/types | **ruff + mypy (strict on core)** | One tool for lint+format; strictness on money-adjacent code | — |
| Data generation | **NumPy (seeded Generator) + custom ring injector** | Full control of distributions; Zipf/log-normal realism | Faker (identity-realistic but no relational ring structure — the structure IS the point) |
| Config | **pydantic-settings + `.env`** | Typed config, fail-fast on missing env | os.getenv sprinkles |

## Dependency Budget (direct, target ≤ 15)

`fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, networkx, boto3, numpy, pytest, coverage, ruff, mypy, httpx` — 13. Every addition must argue its way in.

## Cost Envelope (within $550 credits)

| Item | Estimate |
|------|----------|
| Explanation generation: 1,000 events × ~800 in/out tokens (gpt-oss 120B tier) | < $5 |
| Extraction backfill (Nova Lite) | < $1 |
| Retries/fallback (GLM-5) + dev iterations ×20 | < $40 |
| **Total LLM spend** | **≈ $45–50, ~10× headroom** |

Compute is local; no AWS infra is deployed. Credits are effectively not a constraint — which is itself a design outcome (LLM used surgically, not as the substrate).
