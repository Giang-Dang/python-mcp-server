import asyncio
import hashlib
import json
import logging
import math
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    bindparam,
    cast,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from mcp_server.core.errors import Category, GuardError

from .queries import (
    definition_query,
    definitions_query,
    describe_query,
    diagnostics_query,
    tables_query,
)
from .statements import ProcedureCall


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def hash_definition(definition):
    if definition is None:
        return None
    return hashlib.sha256(definition.replace("\r\n", "\n").encode()).hexdigest()


def database_error(exc, outcome="rolled_back"):
    code = getattr(getattr(exc, "orig", exc), "sqlstate", None)
    category = Category.LIMIT if code in ("57014", "55P03") else Category.DATABASE
    return GuardError(
        category,
        "Statement timed out or exceeded a lock limit."
        if category == Category.LIMIT
        else "Database operation failed; driver details are withheld.",
        outcome,
    )


class Database:
    def __init__(self, engines, batch_engine, settings):
        self.engines, self.batch_engine, self.settings = engines, batch_engine, settings
        self.limits = settings.limits

    async def configure(self, conn, seconds, *, local=True):
        for key, value in (
            ("search_path", "pg_catalog"),
            ("app.tenant_id", str(self.settings.tenant_id)),
            ("statement_timeout", str(int(seconds * 1000))),
            ("lock_timeout", "3000"),
        ):
            await conn.execute(select(func.set_config(key, value, local)))

    @asynccontextmanager
    async def read_connection(self, role="mcp_reader"):
        try:
            async with asyncio.timeout(self.limits.read_seconds):
                async with self.engines[role].connect() as conn, conn.begin():
                    await self.configure(conn, self.limits.read_seconds)
                    yield conn
        except TimeoutError:
            raise GuardError(Category.LIMIT, "Read deadline exceeded.") from None
        except DBAPIError as exc:
            raise database_error(exc, "rejected") from None

    async def preview(self, sql, role):
        async with self.read_connection(role) as conn:
            # SQL is validated pass-through; EXPLAIN never includes ANALYZE.
            result = await conn.exec_driver_sql(
                "EXPLAIN (FORMAT JSON) " + sql, execution_options={"no_parameters": True}
            )
            plan = result.scalar_one()[0]["Plan"]
            if len(json.dumps(plan, ensure_ascii=True).encode()) > self.limits.result_bytes:
                raise GuardError(Category.LIMIT, "Query plan exceeds the result byte limit.")
            return {
                "plan": plan,
                "total_cost_estimate": plan["Total Cost"],
                "rows_estimate": plan["Plan Rows"],
                "estimates_only": True,
            }

    async def collect(self, result):
        columns = list(result.keys())
        rows = []
        used = len(json.dumps(columns, ensure_ascii=True).encode()) + 2
        if used > self.limits.result_bytes:
            raise GuardError(Category.LIMIT, "Result column metadata exceeds the byte limit.")
        reason = None
        async for row in result:
            converted = [json_value(v) for v in row]
            size = len(json.dumps(converted, ensure_ascii=True, separators=(",", ":")).encode()) + 1
            if len(rows) >= self.limits.result_rows:
                reason = "rows"
                break
            if used + size > self.limits.result_bytes:
                reason = "bytes"
                break
            rows.append(converted)
            used += size
        return {
            "columns": columns,
            "rows": rows,
            "returned_rows": len(rows),
            "truncated": reason is not None,
            "truncation_reason": reason,
            "result_bytes": used,
            "byte_scope": "JSON columns and rows",
        }

    async def query(self, sql):
        async with self.read_connection() as conn:
            # SQLAlchemy's async stream() requires an executable, whereas validated text must
            # use exec_driver_sql. Enable a server-side cursor, then wrap its cursor result.
            from sqlalchemy.ext.asyncio import AsyncResult

            result = await conn.run_sync(
                lambda sync: sync.execution_options(
                    stream_results=True, yield_per=1
                ).exec_driver_sql(sql, execution_options={"no_parameters": True})
            )
            stream = AsyncResult(result)
            try:
                return await self.collect(stream)
            finally:
                await stream.close()

    async def fixed(self, statement, role="mcp_reader"):
        async with (
            self.read_connection(role) as conn,
            conn.stream(statement, execution_options={"yield_per": 1}) as stream,
        ):
            return await self.collect(stream)

    async def list_tables(self):
        result = await self.fixed(tables_query(self.settings.schema_name))
        if result["truncated"]:
            raise GuardError(Category.LIMIT, "Catalog exceeds the configured result limits.")
        return [dict(zip(result["columns"], row, strict=True)) for row in result["rows"]]

    async def describe_table(self, name):
        result = await self.fixed(describe_query(name, self.settings.schema_name))
        if not result["rows"]:
            raise GuardError(Category.ARGUMENTS, "Table not found in the configured shop schema.")
        return result

    async def diagnostics(self, kind):
        return await self.fixed(diagnostics_query(kind, self.settings.schema_name), "mcp_monitor")

    async def definition_hash(self, entry, conn=None):
        if conn is not None:
            return hash_definition(
                (await conn.execute(definition_query(entry.signature))).scalar_one()
            )
        async with self.read_connection() as selected:
            return await self.definition_hash(entry, selected)

    async def definitions(self):
        async with self.read_connection() as conn:
            return [
                {**dict(row), "definition_hash": hash_definition(row["definition"])}
                for row in (await conn.execute(definitions_query())).mappings()
            ]

    async def atomic(self, role, statement, before_commit, *, entry=None, seconds=None):
        try:
            async with asyncio.timeout((seconds or self.limits.write_seconds) + 5):
                return await self._atomic(
                    role, statement, before_commit, entry=entry, seconds=seconds
                )
        except TimeoutError:
            raise GuardError(
                Category.LIMIT, "Write deadline exceeded before commit.", "rolled_back"
            ) from None

    async def _atomic(self, role, statement, before_commit, *, entry=None, seconds=None):
        committing = False
        async with self.engines[role].connect() as conn:
            transaction = await conn.begin()
            try:
                await self.configure(conn, seconds or self.limits.write_seconds)
                if entry is not None:
                    entry.check_definition(await self.definition_hash(entry, conn))
                    result = await conn.execute(statement)
                    output = [dict(r) for r in result.mappings()] if result.returns_rows else []
                    payload = {"output": json_value(output)}
                else:
                    result = await conn.exec_driver_sql(
                        statement, execution_options={"no_parameters": True}
                    )
                    count = result.rowcount
                    if count < 0 or count > self.limits.affected_rows:
                        raise GuardError(
                            Category.LIMIT, "Direct affected-row cap exceeded.", "rolled_back"
                        )
                    payload = {
                        "affected_rows": count,
                        "trigger_effects_counted": False,
                        "sequences_restored_on_rollback": False,
                    }
                await before_commit()
                committing = True
                await transaction.commit()
                return {"outcome": "committed", **payload}
            except BaseException as exc:
                if committing:
                    raise GuardError(
                        Category.UNCERTAIN,
                        "Commit acknowledgement was lost. Inspect audit and shop state; do not retry.",
                        "uncertain",
                    ) from None
                try:
                    await asyncio.shield(transaction.rollback())
                except SQLAlchemyError:
                    logging.getLogger(__name__).warning(
                        "Rollback connection lost; no commit was sent."
                    )
                if isinstance(exc, GuardError):
                    raise GuardError(exc.category, str(exc), "rolled_back") from None
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise database_error(exc) from None

    async def mutate(self, sql, before_commit):
        return await self.atomic("mcp_writer", sql, before_commit)

    def call_statement(self, entry, arguments):
        types = {
            "bigint": BigInteger(),
            "integer": Integer(),
            "smallint": SmallInteger(),
            "numeric": Numeric(),
            "text": Text(),
            "date": Date(),
            "bigint[]": ARRAY(BigInteger()),
            "integer[]": ARRAY(Integer()),
        }
        expressions = []
        for p in entry.parameters:
            value = arguments[p.name]
            if value is not None and p.type == "numeric":
                value = Decimal(value)
            if value is not None and p.type == "date":
                value = date.fromisoformat(value)
            expressions.append(cast(bindparam(p.name, value, type_=types[p.type]), types[p.type]))
        return ProcedureCall("shop", entry.name, expressions)

    async def call(self, entry, arguments, before_commit):
        try:
            async with asyncio.timeout(
                min(entry.timeout_seconds, self.limits.procedure_seconds) + 5
            ):
                return await self._call(entry, arguments, before_commit)
        except TimeoutError:
            raise GuardError(
                Category.LIMIT, "Procedure deadline exceeded before execution."
            ) from None

    async def _call(self, entry, arguments, before_commit):
        statement = self.call_statement(entry, arguments)
        seconds = min(entry.timeout_seconds, self.limits.procedure_seconds)
        if entry.transaction_mode == "atomic":
            return await self.atomic(
                entry.role, statement, before_commit, entry=entry, seconds=seconds
            )
        sent = False
        # NullPool plus autocommit: session settings cannot leak into pooled requests.
        async with self.batch_engine.connect() as base:
            conn = await base.execution_options(isolation_level="AUTOCOMMIT")
            try:
                await self.configure(conn, seconds, local=False)
                entry.check_definition(await self.definition_hash(entry, conn))
                await before_commit()
                sent = True
                await conn.execute(statement)
                return {
                    "outcome": "committed",
                    "batch_count": None,
                    "affected_rows": None,
                    "progress": "Procedure completed; individual batch counts are not returned.",
                    "max_batches": arguments["p_max_batches"],
                    "batch_size": arguments["p_batch_size"],
                }
            except BaseException as exc:
                if sent:
                    raise GuardError(
                        Category.UNCERTAIN,
                        "Batch execution interrupted; earlier batches may be committed. Do not retry automatically.",
                        "partially_completed",
                    ) from None
                if isinstance(exc, (GuardError, asyncio.CancelledError)):
                    raise
                raise database_error(exc) from None

    async def close(self):
        for engine in [*self.engines.values(), self.batch_engine]:
            await engine.dispose()
