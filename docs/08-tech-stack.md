# 08: Tech Stack Decisions

Every choice with a justification and what we rejected. Constraint context: local-first, < $550 AWS credits, Bedrock-only LLMs, single builder. **No line-count cap** (owner decision, recorded in doc 02 NFR-6); discipline is maintained by scope rules, not size limits.

| Layer | Choice | Why | Rejected |
|-------|--------|-----|----------|
| Language (core) | **Python 3.12** | Ecosystem for graphs + ML eval + boto3; type hints mature | Node/TS (weaker graph/ML ecosystem for this) |
| API framework | **FastAPI** | Pydantic-native validation = the input contract *is* the schema; async; auto OpenAPI docs | Flask (manual validation), gRPC (overkill for demo) |
| Validation/models | **Pydantic v2** | Rust-fast, strict types, JSON-schema export for the audit trail | dataclasses (no validation) |
| Graph engine | **networkx** | In-process, GraphML persistence, enough for 1k–100k nodes; clean port/adapter to swap | Neo4j local (extra infra + lines), igraph (heavier) |
| Relational store | **SQLite + SQLAlchemy 2** | Zero-config, file-based, append-only triggers for audit; SQLAlchemy keeps the door open to Postgres | Postgres local (infra overhead, no benefit at this scale) |
| LLM inference | **boto3 → AWS Bedrock** (default credential chain) | Required constraint; models: Nova Lite (extraction), gpt-oss 120B w/ GLM-5 fallback (explanation) | LangChain/LangGraph wrapper, unnecessary abstraction for 2 direct Bedrock calls with constrained JSON output; fewer deps, fewer lines, more control. *Deliberate "where not to use a framework" decision* |
| LLM structured output | **Constrained JSON via Bedrock response format + jsonschema validation + 1 retry** | Deterministic pipeline beats agent-style parsing | LLM function-calling frameworks |
| Analyst console (P1) | **Next.js 15 + TypeScript + Tailwind**, react-flow for cluster graphs, recharts for metrics charts; runs locally against FastAPI | **Decision reversed from the original single-file HTML plan, and the reversal is the point:** the original rejection ("build tooling not justified under a line cap") was voided when the owner removed the cap. A real console is the demo surface for 90 seconds of a 5-minute video, matches the builder's strongest stack (Next.js/TS), and the evaluation-report view makes the honest-metrics story visual. Still hard-scoped to 4 views (doc 02) | Single-file HTML (now insufficient for the metrics + replay views), full component library platforms |
| Tests | **pytest + coverage** | Standard, fast, parameterized tests for feature/score cases | unittest (verbose) |
| Lint/types | **ruff + mypy (strict on core)** | One tool for lint+format; strictness on money-adjacent code |, |
| Data generation | **NumPy (seeded Generator) + custom ring injector** | Full control of distributions; Zipf/log-normal realism | Faker (identity-realistic but no relational ring structure, the structure IS the point) |
| Config | **pydantic-settings + `.env`** | Typed config, fail-fast on missing env | os.getenv sprinkles |

## Dependency Budget

Backend (direct, target ≤ 18): `fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, networkx, boto3, numpy, pytest, coverage, ruff, mypy, httpx` (+ `scikit-learn` for the FR-13 baselines). Every addition must argue its way in. Frontend deps live in the console's own `package.json` and are held to the same rule.

## Cost Envelope (within $550 credits)

| Item | Estimate |
|------|----------|
| Explanation generation: 1,000 events × ~800 in/out tokens (gpt-oss 120B tier) | < $5 |
| Extraction backfill (Nova Lite) | < $1 |
| Retries/fallback (GLM-5) + dev iterations ×20 | < $40 |
| **Total LLM spend** | **≈ $45–50, ~10× headroom** |

Compute is local; no AWS infra is deployed. Credits are effectively not a constraint, which is itself a design outcome (LLM used surgically, not as the substrate).

**Cost caveat:** per-token prices vary by Bedrock region and model tier; the estimates above assume the cheapest available tier for each model. The Phase 0 model-verification calls (below) also record actual observed pricing/latency, and the envelope is updated then. If gpt-oss 120B proves unavailable or materially pricier in the configured region, the fallback chain (doc 03) already routes to gpt-oss-20B / GLM-5 / Llama 3.3 70B, all cheaper, with no architecture change.

## Appendix, Model Verification Log (measured 2026-08-22, us-east-1)

The design assumed all candidate models honor constrained/structured JSON output on Bedrock comparably. **Measured on day one with one bounded call per model** (`scripts/verify_models.py`; discovery via the free control-plane API, at most one inference per model per run). Results:

| Model | Bedrock model ID (live) | Constrained JSON | Latency (1 call) | Quality note | Verdict |
|-------|-------------------------|------------------|------------------|--------------|---------|
| gpt-oss 120B | `openai.gpt-oss-120b-1:0` | prompt-only (native responseFormat rejected) | 7,235 ms | valid JSON; reasoning model needs ≥512 maxTokens or returns empty text | Primary explanation model; async by design, so latency acceptable |
| gpt-oss 20B | `openai.gpt-oss-20b-1:0` | prompt-only | 1,360 ms | valid JSON | FALLBACK_1 |
| GLM-5 | `zai.glm-5` | prompt-only | 703 ms | valid JSON, unfenced | FALLBACK_2 (fastest full-quality fallback) |
| Nova Lite | `amazon.nova-lite-v1:0` | prompt-only | 514 ms | valid JSON, wrapped in markdown fences | Extraction model |
| Llama 3.3 70B | `meta.llama3-3-70b-instruct-v1:0` | not invocable | n/a | listed in-region but Converse rejects the base ID (needs a cross-region inference profile) | Out of the chain; GLM-5 keeps the final fallback slot |

**Conclusions feeding Phase 5 (this is why the log exists):**

1. **No candidate supports native `responseFormat` JSON on Bedrock.** The Phase 5 pipeline must be prompt-based JSON + markdown-fence stripping + jsonschema validation + a single structured retry. The doc 05/06 design is confirmed; fence-stripping is now a hard requirement (Nova and GLM both fence).
2. **gpt-oss models are reasoning models**: a 128-token budget produced empty output (all tokens spent thinking). Phase 5 uses ≥512 maxTokens for explanation calls and must not parse empty text as failure-to-comply without checking the stop reason.
3. **Latency spread is 14x** (514 ms Nova vs 7.2 s gpt-oss-120b). Explanations stay async; batch backfill must be concurrent, not serial, or 1,000 explanations at 7 s would take ~2 hours.
4. **The earlier "prefer llama-3.3-70b in US regions" note is measured-wrong for us-east-1**: the model is listed but its base ID is not invocable there. Chain stays gpt-oss-120b → gpt-oss-20b → glm-5.

Total verification spend: 3 bounded runs, ~15 calls of ≤512 tokens, well under $0.10 of the $20 budget.
