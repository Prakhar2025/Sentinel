"""FastAPI service (docs/06 API specification).

Security model:
- Standard scope: X-API-Key or a per-merchant JWT bearer token. JWT
  callers can ingest and read only their own merchant's traffic.
- Admin scope: X-Admin-Key, the only caller that can unmask PII or see
  raw cross-merchant entity lists; every admin action is written to the
  audit store with the caller's scope label, never the key value.
- Public-demo mode (settings.public_demo): admin routes and unmasking
  return 404 structurally, requests are per-IP rate limited, and live
  narrative generation is daily-capped (docs/07 hardening).
- Phones are masked in every response unless ?unmask=true AND admin
  scope, which is audit-logged.

Degradation ladder (doc 10): store failures spool the event to disk and
return 503 STORE_UNAVAILABLE; the process never raises past a request
boundary and never auto-blocks on failure. The identity graph rebuilds
from stored events on startup (event sourcing).
"""

from __future__ import annotations

import hmac
import json
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .auth import MerchantIdentity, verify_token
from .challenger import ChallengerModel
from .config import Settings, get_settings
from .data.models import PaymentEvent, PaymentMethod, PriorOutcome
from .explain_api import DailyCap, RateLimiter
from .features import extract_features
from .graph import GraphStore, NodeType, entities_of
from .observability import MetricsRegistry, new_request_id
from .store import SCHEMA_VERSION, AuditStore, StoreUnavailableError
from .verdict import Verdict, VerdictEngine, verdict_to_json

BATCH_LIMIT = 1000
ENTITY_TYPES = {
    "upi": NodeType.UPI,
    "phone": NodeType.PHONE,
    "device": NodeType.DEVICE,
    "email": NodeType.EMAIL,
}


class FeedbackIn(BaseModel):
    """Analyst feedback request (P2 stub, append-only)."""

    verdict_id: str
    analyst_decision: str
    note: str | None = None


class Problem(BaseModel):
    """RFC 7807-style error body."""

    type: str
    title: str
    status: int
    detail: str | None = None


def problem(status: int, type_id: str, title: str, detail: str | None = None) -> JSONResponse:
    """Uniform problem-JSON error response."""
    return JSONResponse(
        status_code=status,
        content=Problem(type=type_id, title=title, status=status, detail=detail).model_dump(),
    )


def mask_phone(phone: str | None) -> str | None:
    """+9198XXXX5678 style mask (docs/06)."""
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return "X" * len(phone)
    return f"+{digits[:4]}XXXX{digits[-4:]}"


def load_model_config(path: Path) -> tuple[dict[str, int], dict[str, int], str] | None:
    """Load locked calibration if present; None keeps code defaults."""
    if not path.exists():
        return None
    config = json.loads(path.read_text(encoding="utf-8"))
    return config["weights"], config["thresholds"], config["model_version"]


def _event_row(event: PaymentEvent) -> dict[str, Any]:
    """Persistable row for the events table."""
    return {
        "event_id": event.event_id,
        "merchant_id": event.merchant_id,
        "customer_id": event.customer_id,
        "amount_paise": event.amount_paise,
        "upi_vpa": event.upi_vpa,
        "phone": event.phone,
        "device_id": event.device_id,
        "email": event.email,
        "ip": event.ip,
        "payment_method": event.payment_method.value,
        "prior_outcome": event.prior_outcome.value if event.prior_outcome else None,
        "ts": event.ts.isoformat(),
    }


def _row_merchant(row: dict[str, Any]) -> str | None:
    """Best-effort merchant lookup from a stored verdict's evidence."""
    evidence = row.get("evidence") or {}
    if isinstance(evidence, dict):
        return evidence.get("merchant_id")
    return None


def _is_admin_path(path: str) -> bool:
    """Routes unavailable on the public demo regardless of headers."""
    return "/full" in path


def _rebuild_graph_from_store(store: AuditStore) -> GraphStore:
    """Replay stored events into a fresh graph (event sourcing).

    Without this, a restart serves an empty in-memory graph while the
    audit store holds thousands of events. Rebuild is chronological by
    ingestion order, matching online semantics.
    """
    graph = GraphStore()
    for row in store.all_events():
        event = PaymentEvent(
            event_id=row["event_id"],
            merchant_id=row["merchant_id"],
            customer_id=row["customer_id"],
            amount_paise=row["amount_paise"],
            upi_vpa=row["upi_vpa"],
            phone=row["phone"],
            device_id=row["device_id"],
            email=row["email"],
            ip=row["ip"],
            ts=datetime.fromisoformat(row["ts"]),
            payment_method=PaymentMethod(row["payment_method"]),
            prior_outcome=PriorOutcome(row["prior_outcome"]) if row["prior_outcome"] else None,
        )
        graph.upsert_event(event, entities_of(event))
    return graph


_SCENARIO_CACHE: dict[str, Any] = {}


def _demo_scenario_cached(seed: int = 42) -> dict[str, Any]:
    """Largest standard ring from the dataset, as serving-shaped events.

    Cached per process; deterministic for the seed.
    """
    key = f"seed:{seed}"
    if key in _SCENARIO_CACHE:
        cached: dict[str, Any] = _SCENARIO_CACHE[key]
        return cached
    from .data.generate import generate_dataset

    events, labels, _ = generate_dataset(seed=seed)
    label_by_id = {label.event_id: label for label in labels}
    rings: dict[str, list[PaymentEvent]] = {}
    for event in events:
        label = label_by_id[event.event_id]
        strategy = label.ring_strategy.value if label.ring_strategy else ""
        if label.is_fraud and label.ring_id and strategy == "standard":
            rings.setdefault(label.ring_id, []).append(event)
    # Pick the ring hitting the most merchants; ties by event count then id.
    chosen_id, chosen = max(
        rings.items(),
        key=lambda pair: (
            len({e.merchant_id for e in pair[1]}),
            len(pair[1]),
            -int(pair[0].split("_")[1]),
        ),
    )
    ordered = sorted(chosen, key=lambda e: e.ts)
    scenario = {
        "ring_id": chosen_id,
        "strategy": "standard",
        "merchants": sorted({e.merchant_id for e in ordered}),
        "events": [json.loads(e.model_dump_json()) for e in ordered],
    }
    _SCENARIO_CACHE[key] = scenario
    return scenario


def create_app(
    settings: Settings | None = None,
    store: AuditStore | None = None,
    engine: VerdictEngine | None = None,
    graph: GraphStore | None = None,
    challenger: ChallengerModel | None = None,
    enable_challenger: bool = True,
) -> FastAPI:
    """Build the service. Every dependency is injectable for tests."""
    app_settings = settings or get_settings()
    app = FastAPI(title="Abuse-Ring Sentinel", version="1", docs_url="/docs")
    app.state.settings = app_settings
    app.state.store = store or AuditStore(Path("sentinel.db"))
    app.state.graph = graph or _rebuild_graph_from_store(app.state.store)
    if engine is None:
        locked = load_model_config(Path(app_settings.model_config_path))
        if locked is None:
            app.state.engine = VerdictEngine()
        else:
            weights, thresholds, version = locked
            app.state.engine = VerdictEngine(
                weights=weights,
                review_threshold=thresholds["review"],
                block_threshold=thresholds["block"],
                model_version=version,
            )
    else:
        app.state.engine = engine
    # Shadow challenger: records its opinion next to every verdict and
    # never influences the decision (docs/14). Loaded from the artifact
    # when present; injectable for tests.
    app.state.challenger = (
        (challenger or ChallengerModel.load(Path(app_settings.challenger_model_path)))
        if enable_challenger
        else None
    )
    app.state.metrics = MetricsRegistry()
    app.state.public_demo = app_settings.public_demo
    app.state.rate_limiter = RateLimiter(
        app_settings.rate_limit_requests, app_settings.rate_limit_window_seconds
    )
    app.state.explain_cap = DailyCap(
        Path(app_settings.explain_cap_path), app_settings.explain_daily_cap
    )

    # The analyst console is a separate local origin; CORS is scoped to
    # exactly that origin (docs/07: no wildcard).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.console_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "X-Admin-Key", "X-Request-Id", "Content-Type"],
    )

    @app.middleware("http")
    async def telemetry(request: Request, call_next: Callable[[Request], Any]) -> Any:
        """Request id + counters + latency histogram; best-effort only."""
        request_id = request.headers.get("X-Request-Id") or new_request_id()
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        try:
            app.state.metrics.inc("sentinel_http_requests_total")
            if request.url.path == "/v1/events" and request.method == "POST":
                app.state.metrics.observe(
                    "sentinel_event_latency_seconds", time.perf_counter() - started
                )
        except Exception:  # telemetry must never break serving
            pass
        return response

    @app.middleware("http")
    async def public_guard(request: Request, call_next: Callable[[Request], Any]) -> Any:
        """Per-IP rate limiting for the hosted demo; admin surface
        structurally disabled when public_demo is set."""
        if app.state.public_demo:
            if not app.state.rate_limiter.allow(app.state.rate_limiter.client_key(request)):
                return problem(
                    429, "RATE_LIMITED", "too many requests", "slow down and retry shortly"
                )
            if _is_admin_path(request.url.path):
                return problem(404, "NOT_FOUND", "not available in the public demo", None)
        return await call_next(request)

    # ------------------------------------------------------------- auth deps

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if x_api_key is None or not hmac.compare_digest(x_api_key, app_settings.sentinel_api_key):
            raise HTTPException(status_code=401, detail="missing or invalid API key")

    def require_admin_key(x_admin_key: Annotated[str | None, Header()] = None) -> None:
        if app.state.public_demo:
            raise HTTPException(status_code=404, detail="not available in the public demo")
        if x_admin_key is None or not hmac.compare_digest(
            x_admin_key, app_settings.sentinel_admin_api_key
        ):
            raise HTTPException(status_code=403, detail="this operation requires the admin key")

    def admin_key_valid(x_admin_key: str | None) -> bool:
        return x_admin_key is not None and hmac.compare_digest(
            x_admin_key, app_settings.sentinel_admin_api_key
        )

    def caller_identity(
        authorization: Annotated[str | None, Header()] = None,
    ) -> MerchantIdentity | None:
        """Verified merchant identity when a valid bearer token is used."""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        return verify_token(app_settings.jwt_secret, authorization[7:])

    def require_api_or_bearer(
        x_api_key: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> MerchantIdentity | None:
        """Standard authN: demo key OR a verified merchant JWT.

        Returns the merchant identity when JWT was used, enabling
        per-merchant scoping downstream; None for key auth (demo scope).
        """
        if x_api_key is not None and hmac.compare_digest(x_api_key, app_settings.sentinel_api_key):
            return None
        identity = caller_identity(authorization)
        if identity is not None:
            return identity
        raise HTTPException(status_code=401, detail="missing or invalid credentials")

    # -------------------------------------------------------------- helpers

    def spool(event: PaymentEvent) -> None:
        spool_dir = Path(app_settings.spool_dir)
        spool_dir.mkdir(parents=True, exist_ok=True)
        with (spool_dir / "ingest.spool").open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def shadow_opinion(
        verdict: Verdict, event: PaymentEvent | None
    ) -> dict[str, float | int | bool] | None:
        if app.state.challenger is None or event is None or verdict.degraded:
            return None
        features = extract_features(event, app.state.graph)
        if features is None:
            return None
        opinion: dict[str, float | int | bool] = app.state.challenger.predict(features)
        return opinion

    def persist(
        verdict: Verdict,
        event: PaymentEvent,
        shadow: dict[str, float | int | bool] | None = None,
    ) -> None:
        payload = verdict_to_json(verdict)
        evidence = {
            **payload["evidence"],
            "customer_id": event.customer_id,
            "merchant_id": event.merchant_id,
        }
        app.state.store.insert_verdict(
            {
                "event_id": verdict.event_id,
                "score": verdict.score,
                "verdict": verdict.verdict,
                "reason_codes": payload["reason_codes"],
                "evidence": evidence,
                "features": payload["features"],
                "contributions": payload["contributions"],
                "model_version": payload["model_version"],
                "explanation_status": "PENDING",
                "challenger": shadow,
            }
        )

    # --------------------------------------------------------------- routes

    @app.post("/v1/events", dependencies=[Depends(require_api_or_bearer)])
    def ingest_event(
        event: PaymentEvent,
        identity: MerchantIdentity | None = Depends(require_api_or_bearer),
    ) -> Any:
        if identity is not None and identity.merchant_id != event.merchant_id:
            return problem(
                403,
                "MERCHANT_MISMATCH",
                "merchant tokens may only ingest their own events",
                f"token merchant {identity.merchant_id} != event merchant {event.merchant_id}",
            )
        try:
            inserted = app.state.store.insert_event(_event_row(event))
            if not inserted:
                prior = app.state.store.get_verdict(event.event_id)
                merged: dict[str, Any] = {
                    "type": "DUPLICATE_EVENT",
                    "title": "event already ingested",
                    "status": 409,
                    "detail": "prior verdict attached",
                    "verdict": prior,
                }
                return JSONResponse(status_code=409, content=merged)
            app.state.graph.upsert_event(event, entities_of(event))
            verdict = app.state.engine.score_event(event, app.state.graph)
            shadow = shadow_opinion(verdict, event)
            persist(verdict, event, shadow)
            app.state.metrics.inc("sentinel_events_total")
            app.state.metrics.inc("sentinel_verdicts_total", band=verdict.verdict.lower())
            if verdict.degraded:
                app.state.metrics.inc("sentinel_degraded_total")
            app.state.metrics.observe_score(verdict.score)
            return {
                **verdict_to_json(verdict),
                "challenger": shadow,
                "explanation_status": "PENDING",
                "schema_version": SCHEMA_VERSION,
                "duplicate": False,
            }
        except StoreUnavailableError:
            spool(event)
            return problem(
                503,
                "STORE_UNAVAILABLE",
                "audit store unavailable",
                "event spooled to disk for replay; re-ingest later",
            )

    @app.post("/v1/events:batch", dependencies=[Depends(require_api_or_bearer)])
    def ingest_batch(events: list[PaymentEvent]) -> Any:
        if len(events) > BATCH_LIMIT:
            return problem(
                400, "BATCH_TOO_LARGE", "batch exceeds limit", f"max {BATCH_LIMIT} events"
            )
        results: list[dict[str, Any]] = []
        accepted = duplicated = spooled = 0
        for index, event in enumerate(events):
            try:
                inserted = app.state.store.insert_event(_event_row(event))
                if not inserted:
                    duplicated += 1
                    results.append(
                        {
                            "index": index,
                            "status": "duplicate",
                            "verdict": app.state.store.get_verdict(event.event_id),
                        }
                    )
                    continue
                app.state.graph.upsert_event(event, entities_of(event))
                verdict = app.state.engine.score_event(event, app.state.graph)
                shadow = shadow_opinion(verdict, event)
                persist(verdict, event, shadow)
                accepted += 1
                app.state.metrics.inc("sentinel_events_total")
                app.state.metrics.observe_score(verdict.score)
                results.append(
                    {
                        "index": index,
                        "status": "accepted",
                        "verdict": {**verdict_to_json(verdict), "challenger": shadow},
                    }
                )
            except StoreUnavailableError:
                spool(event)
                spooled += 1
                results.append({"index": index, "status": "spooled", "detail": "store unavailable"})
        return {
            "accepted": accepted,
            "duplicate": duplicated,
            "spooled": spooled,
            "results": results,
        }

    @app.get("/v1/verdicts/{event_id}", dependencies=[Depends(require_api_or_bearer)])
    def get_verdict(event_id: str) -> Any:
        verdict = app.state.store.get_verdict(event_id)
        if verdict is None:
            return problem(404, "NOT_FOUND", "unknown event", f"no verdict for {event_id}")
        return verdict

    @app.get("/v1/verdicts", dependencies=[Depends(require_api_or_bearer)])
    def queue(
        verdict: str | None = Query(default=None),
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        identity: MerchantIdentity | None = Depends(require_api_or_bearer),
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = app.state.store.list_verdicts(verdict=verdict, limit=limit)
        if identity is not None:
            # JWT callers see only their own traffic (federated privacy,
            # docs/07): other merchants' event rows are filtered out.
            rows = [row for row in rows if _row_merchant(row) == identity.merchant_id]
        return rows

    @app.get(
        "/v1/risk/entities/{entity_type}/{entity_value}",
        dependencies=[Depends(require_api_or_bearer)],
    )
    def entity_risk(entity_type: str, entity_value: str) -> Any:
        node_type = ENTITY_TYPES.get(entity_type)
        if node_type is None:
            return problem(
                400, "BAD_ENTITY_TYPE", "unknown entity type", f"use one of {sorted(ENTITY_TYPES)}"
            )
        attrs = app.state.graph.node_attrs(node_type, entity_value)
        if attrs is None:
            return problem(404, "NOT_FOUND", "entity not in graph", entity_value)
        return {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "federated_signal": {
                "linked_merchant_count": int(attrs["merchant_count"]),
                "max_cross_merchant_fanout": int(attrs["merchant_count"]),
                "linked_identity_count": int(attrs["linked_identity_count"]),
                "fraud_taint": float(attrs["fraud_taint"]),
                "last_seen_epoch": float(attrs["last_seen"]),
            },
        }

    @app.get(
        "/v1/risk/entities/{entity_type}/{entity_value}/full",
        dependencies=[Depends(require_api_or_bearer), Depends(require_admin_key)],
    )
    def entity_risk_full(entity_type: str, entity_value: str) -> Any:
        node_type = ENTITY_TYPES.get(entity_type)
        if node_type is None:
            return problem(400, "BAD_ENTITY_TYPE", "unknown entity type", None)
        node = f"{node_type.value}:{entity_value}"
        if not app.state.graph.has_node(node):
            return problem(404, "NOT_FOUND", "entity not in graph", entity_value)
        app.state.store.admin_audit(action="entity_full_lookup", entity=node, scope="admin")
        return {
            "entity": node,
            "linked_nodes": app.state.graph.undirected_neighbors(node),
            "node_attrs": app.state.graph.raw_node_attrs(node),
        }

    @app.get("/v1/graph/cluster/{customer_id}", dependencies=[Depends(require_api_or_bearer)])
    def cluster_view(
        customer_id: str,
        unmask: bool = False,
        x_admin_key: Annotated[str | None, Header()] = None,
    ) -> Any:
        nodes, truncated = app.state.graph.cluster(customer_id)
        if not nodes:
            return problem(404, "NOT_FOUND", "unknown customer", customer_id)
        if unmask and app.state.public_demo:
            return problem(404, "NOT_FOUND", "not available in the public demo", None)
        if unmask and not admin_key_valid(x_admin_key):
            raise HTTPException(status_code=403, detail="unmasking requires the admin key")
        if unmask:
            app.state.store.admin_audit(
                action="unmask_cluster", entity=f"customer:{customer_id}", scope="admin"
            )
        node_payloads = []
        for node in nodes:
            attrs = app.state.graph.raw_node_attrs(node) or {}
            kind, _, value = node.partition(":")
            if kind == "phone" and not unmask:
                value = mask_phone(value) or value
            node_payloads.append(
                {"type": kind, "id": value, "taint": attrs.get("fraud_taint", 0.0)}
            )
        edges = [
            {"source": node, "target": target}
            for node in nodes
            for target in app.state.graph.successors(node)
        ]
        return {
            "customer_id": customer_id,
            "nodes": node_payloads,
            "edges": edges,
            "truncated": truncated,
        }

    @app.post("/v1/feedback", dependencies=[Depends(require_api_or_bearer)], status_code=202)
    def feedback(payload: FeedbackIn) -> Any:
        verdict = app.state.store.get_verdict_by_id(payload.verdict_id)
        if verdict is None:
            return problem(404, "NOT_FOUND", "unknown verdict", "verdict_id does not exist")
        if payload.analyst_decision not in {"CONFIRM_FRAUD", "CLEAR", "UNKNOWN"}:
            return problem(
                400, "BAD_DECISION", "invalid decision", "CONFIRM_FRAUD | CLEAR | UNKNOWN"
            )
        app.state.store.insert_feedback(
            verdict["verdict_id"], payload.analyst_decision, payload.note
        )
        return {"status": "recorded"}

    @app.get("/v1/evaluation", dependencies=[Depends(require_api_or_bearer)])
    def evaluation() -> Any:
        """Serve the last evaluation artifacts (read-only, for the console)."""
        metrics_path = Path("evaluation/metrics.json")
        latency_path = Path("evaluation/latency.json")
        if not metrics_path.exists():
            return problem(
                404,
                "NOT_EVALUATED",
                "no evaluation artifacts",
                "run `make evaluate` to generate evaluation/metrics.json",
            )
        payload: dict[str, Any] = {"metrics": json.loads(metrics_path.read_text(encoding="utf-8"))}
        if latency_path.exists():
            payload["latency"] = json.loads(latency_path.read_text(encoding="utf-8"))
        return payload

    @app.get("/v1/demo/scenario", dependencies=[Depends(require_api_or_bearer)])
    def demo_scenario() -> Any:
        """The scripted ring-caught-across-merchants story for the replay view.

        Deterministic: largest standard ring from the seed-42 dataset,
        serving-shaped events only (no labels cross the boundary).
        """
        return _demo_scenario_cached()

    @app.post("/v1/explain/{event_id}", dependencies=[Depends(require_api_or_bearer)])
    def explain_live(event_id: str) -> Any:
        """Generate one narrative live (Bedrock) under the daily cap.

        Cap exhausted or generation failure -> serves the stored
        narrative with an explicit status; the visitor never sees an
        error. AWS runs server-side only; the frontend never touches
        credentials.
        """
        stored = app.state.store.get_verdict(event_id)
        if stored is None:
            return problem(404, "NOT_FOUND", "unknown event", event_id)
        if not app.state.explain_cap.try_acquire():
            return {
                "event_id": event_id,
                "explanation": stored.get("explanation"),
                "explanation_status": "CAP_REACHED",
                "cap": app.state.explain_cap.status(),
            }
        from .backfill import build_service
        from .explain import CostLog

        cost_log = CostLog(Path("evaluation/llm_cost.jsonl"))
        service = build_service(app_settings, cost_log)
        result = service.explain(stored)
        if result.status == "DONE" and result.narrative is not None:
            app.state.store.set_explanation(event_id, result.narrative, "DONE")
            return {
                "event_id": event_id,
                "explanation": result.narrative,
                "explanation_status": "DONE",
                "cap": app.state.explain_cap.status(),
            }
        return {
            "event_id": event_id,
            "explanation": stored.get("explanation"),
            "explanation_status": "SKIPPED",
            "cap": app.state.explain_cap.status(),
        }

    @app.get("/metrics", dependencies=[Depends(require_api_key)])
    def metrics_endpoint() -> Response:
        return Response(content=app.state.metrics.render(), media_type="text/plain")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> Any:
        store_ok = app.state.store.healthy()
        body = {
            "store": "ok" if store_ok else "unavailable",
            "graph_nodes": app.state.graph.size,
            "llm": "optional",
        }
        return body if store_ok else JSONResponse(status_code=503, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(400, "VALIDATION_FAILED", "request validation failed", str(exc.errors()[:3]))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return problem(exc.status_code, "HTTP_ERROR", str(exc.detail), None)

    return app


__all__ = ["create_app", "load_model_config", "mask_phone"]
