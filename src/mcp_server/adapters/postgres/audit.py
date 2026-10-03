from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, func, insert
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="audit")
operations = Table(
    "operations",
    metadata,
    Column("operation_id", String, primary_key=True),
    Column("issuer", String),
    Column("subject", String),
    Column("expires_at", DateTime(timezone=True)),
    Column("tool", String),
    Column("inputs", JSONB),
    Column("limits", JSONB),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
events = Table(
    "events",
    metadata,
    Column("event_id", BigInteger, primary_key=True),
    Column("operation_id", String),
    Column("kind", String),
    Column("detail", JSONB),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


class PostgresAudit:
    def __init__(self, engine):
        self.engine = engine

    async def start(self, operation):
        async with self.engine.begin() as conn:
            await conn.execute(
                insert(operations).values(
                    operation_id=operation.id,
                    issuer=operation.principal.issuer,
                    subject=operation.principal.subject,
                    expires_at=datetime.fromtimestamp(operation.principal.expires_at, UTC),
                    tool=operation.tool,
                    inputs=operation.inputs,
                    limits=operation.limits,
                )
            )

    async def event(self, operation_id, kind, detail):
        async with self.engine.begin() as conn:
            await conn.execute(
                insert(events).inline().values(operation_id=operation_id, kind=kind, detail=detail)
            )
