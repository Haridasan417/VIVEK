"""Feedback/event storage.

Uses SQLAlchemy Core so the same code works against SQLite (local dev, zero
setup) and PostgreSQL (production, via DATABASE_URL env var) without changes.

Local dev:      no DATABASE_URL set -> sqlite:///vivek_feedback.db
Render/prod:    DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname
                (Render's "Internal Database URL" for a managed Postgres works
                directly here — just paste it into the env var.)
"""
import json
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
)

metadata = MetaData()

analysis_events = Table(
    "analysis_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime, nullable=False),
    Column("source", String(64), nullable=False),
    Column("modalities", Text, nullable=False),
    Column("score", Integer, nullable=False),
    Column("action", String(32), nullable=False),
    Column("reasons", Text, nullable=False),
    Column("matched_pattern_id", String(64), nullable=True),
)


class FeedbackStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///vivek_feedback.db")
        # Render (and some hosts) hand out "postgres://" URLs; SQLAlchemy 2.x needs "postgresql://".
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine = create_engine(self.database_url, connect_args=connect_args)
        metadata.create_all(self.engine)

    def record(
        self,
        source: str,
        modalities: list[str],
        score: int,
        action: str,
        reasons: list[str],
        matched_pattern_id: str | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(analysis_events).values(
                    created_at=datetime.now(timezone.utc),
                    source=source,
                    modalities=json.dumps(modalities),
                    score=score,
                    action=action,
                    reasons=json.dumps(reasons),
                    matched_pattern_id=matched_pattern_id,
                )
            )
