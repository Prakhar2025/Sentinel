"""SQLite audit store (docs/04 relational schema).

Append-heavy audit trail: events, verdicts (one per event, immutable),
analyst feedback (append-only), and an admin audit log for every
privileged action (unmasking, raw entity lookups). The admin log records
the caller's scope label, never the raw key value.

SQLite runs in WAL mode with foreign keys enforced (doc 10, R4/P7).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Engine, create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = "1"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base for the audit schema."""


class EventRow(Base):
    """Immutable record of every accepted event."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(primary_key=True)
    merchant_id: Mapped[str] = mapped_column()
    customer_id: Mapped[str] = mapped_column()
    amount_paise: Mapped[int] = mapped_column()
    upi_vpa: Mapped[str | None] = mapped_column(default=None)
    phone: Mapped[str | None] = mapped_column(default=None)
    device_id: Mapped[str | None] = mapped_column(default=None)
    email: Mapped[str | None] = mapped_column(default=None)
    ip: Mapped[str | None] = mapped_column(default=None)
    payment_method: Mapped[str] = mapped_column()
    prior_outcome: Mapped[str | None] = mapped_column(default=None)
    ts: Mapped[str] = mapped_column()
    ingested_at: Mapped[str] = mapped_column(default=_utcnow)


class VerdictRow(Base):
    """One verdict per event; append-only, never mutated."""

    __tablename__ = "verdicts"

    verdict_id: Mapped[str] = mapped_column(default=_uuid, primary_key=True)
    event_id: Mapped[str] = mapped_column(unique=True)
    score: Mapped[int] = mapped_column()
    verdict: Mapped[str] = mapped_column()
    reason_codes: Mapped[list[str]] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    features: Mapped[dict[str, Any]] = mapped_column(JSON)
    contributions: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column()
    schema_version: Mapped[str] = mapped_column(default=SCHEMA_VERSION)
    explanation: Mapped[str | None] = mapped_column(default=None)
    explanation_status: Mapped[str] = mapped_column(default="PENDING")
    challenger: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[str] = mapped_column(default=_utcnow)


class FeedbackRow(Base):
    """Analyst feedback; append-only future training signal."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(default=_uuid, primary_key=True)
    verdict_id: Mapped[str] = mapped_column()
    analyst_decision: Mapped[str] = mapped_column()
    note: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[str] = mapped_column(default=_utcnow)


class AdminAuditRow(Base):
    """Audit trail for privileged actions (scope label only, never keys)."""

    __tablename__ = "admin_audit"

    id: Mapped[str] = mapped_column(default=_uuid, primary_key=True)
    action: Mapped[str] = mapped_column()
    entity: Mapped[str] = mapped_column()
    scope: Mapped[str] = mapped_column()
    created_at: Mapped[str] = mapped_column(default=_utcnow)


class StoreUnavailableError(RuntimeError):
    """Raised when the audit store cannot service a request."""


class AuditStore:
    """Typed wrapper over the SQLite audit schema."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self._engine, "connect")
        def _set_pragmas(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self._engine)
        self._migrate_verdicts_challenger()

    def _migrate_verdicts_challenger(self) -> None:
        """Add the shadow-opinion column to pre-v2 verdicts tables."""
        from sqlalchemy import inspect, text

        inspector = inspect(self._engine)
        columns = {column["name"] for column in inspector.get_columns("verdicts")}
        if "challenger" not in columns:
            with self._engine.begin() as connection:
                connection.execute(text("ALTER TABLE verdicts ADD COLUMN challenger JSON"))

    # ------------------------------------------------------------------ write

    def insert_event(self, payload: dict[str, Any]) -> bool:
        """Insert an event; False when the event_id already exists."""
        from sqlalchemy import insert

        try:
            with self._engine.begin() as connection:
                result = connection.execute(
                    insert(EventRow).values(**payload).prefix_with("OR IGNORE")
                )
                return result.rowcount > 0
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc

    def insert_verdict(self, payload: dict[str, Any]) -> None:
        from sqlalchemy import insert

        try:
            with self._engine.begin() as connection:
                connection.execute(insert(VerdictRow).values(**payload))
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc

    def set_explanation(self, event_id: str, explanation: str, status: str) -> None:
        """Attach the LLM narrative to an existing verdict (backfill)."""
        from sqlalchemy import update

        try:
            with self._engine.begin() as connection:
                connection.execute(
                    update(VerdictRow)
                    .where(VerdictRow.event_id == event_id)
                    .values(explanation=explanation, explanation_status=status)
                )
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc

    def pending_explanations(self, limit: int) -> list[dict[str, Any]]:
        """Verdicts still awaiting a narrative, highest score first."""
        statement = (
            select(VerdictRow)
            .where(VerdictRow.explanation_status == "PENDING")
            .order_by(VerdictRow.score.desc())
            .limit(limit)
        )
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(statement).mappings().all()
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc
        return [self._public_verdict(dict(row)) for row in rows]

    def insert_feedback(self, verdict_id: str, decision: str, note: str | None) -> None:
        from sqlalchemy import insert

        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(FeedbackRow).values(
                        verdict_id=verdict_id, analyst_decision=decision, note=note
                    )
                )
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc

    def admin_audit(self, action: str, entity: str, scope: str) -> None:
        from sqlalchemy import insert

        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(AdminAuditRow).values(action=action, entity=entity, scope=scope)
                )
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc

    # ------------------------------------------------------------------- read

    def get_verdict(self, event_id: str) -> dict[str, Any] | None:
        """Fetch a verdict by its event id."""
        try:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(select(VerdictRow).where(VerdictRow.event_id == event_id))
                    .mappings()
                    .first()
                )
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc
        if row is None:
            return None
        result: dict[str, Any] = dict(row)
        return self._public_verdict(result)

    def get_verdict_by_id(self, verdict_id: str) -> dict[str, Any] | None:
        """Fetch a verdict by its own id (feedback and audit flows)."""
        try:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(
                        select(VerdictRow).where(VerdictRow.verdict_id == verdict_id)
                    )
                    .mappings()
                    .first()
                )
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc
        if row is None:
            return None
        return self._public_verdict(dict(row))

    def list_verdicts(self, verdict: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        statement = select(VerdictRow).order_by(VerdictRow.score.desc()).limit(limit)
        if verdict:
            statement = statement.where(VerdictRow.verdict == verdict)
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(statement).mappings().all()
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc
        return [self._public_verdict(dict(row)) for row in rows]

    def verdict_event_exists(self, event_id: str) -> bool:
        return self.get_verdict(event_id) is not None

    def all_events(self) -> list[dict[str, Any]]:
        """All stored events in ingestion order (graph rebuild on startup)."""
        statement = select(EventRow).order_by(EventRow.ingested_at, EventRow.event_id)
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(statement).mappings().all()
        except OperationalError as exc:
            raise StoreUnavailableError(str(exc)) from exc
        return [dict(row) for row in rows]

    def healthy(self) -> bool:
        from sqlalchemy import text

        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except OperationalError:
            return False

    def close(self) -> None:
        """Dispose connection pools; required on Windows before unlinking."""
        self._engine.dispose()

    @staticmethod
    def _public_verdict(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "verdict_id": row["verdict_id"],
            "event_id": row["event_id"],
            "score": row["score"],
            "verdict": row["verdict"],
            "reason_codes": row["reason_codes"],
            "evidence": row["evidence"],
            "features": row["features"],
            "contributions": row["contributions"],
            "model_version": row["model_version"],
            "schema_version": row["schema_version"],
            "explanation": row.get("explanation"),
            "explanation_status": row["explanation_status"],
            "challenger": row.get("challenger"),
            "created_at": row["created_at"],
        }


__all__ = [
    "AdminAuditRow",
    "AuditStore",
    "EventRow",
    "FeedbackRow",
    "StoreUnavailableError",
    "VerdictRow",
]
