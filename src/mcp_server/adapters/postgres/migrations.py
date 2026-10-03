"""Only the audit administration CLI accepts migration-owner credentials."""

from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

metadata = MetaData()
versions = Table(
    "mcp_audit_migrations",
    metadata,
    Column("version", Integer, primary_key=True),
    Column("filename", String),
    Column("sha256", String),
)


def migrate(url_text: str, directory: Path, apply: bool = False):
    import hashlib

    url = make_url(url_text)
    if url.username != "mcp_audit_owner" or url.database != "mcp_audit":
        raise ValueError("Migrations require mcp_audit_owner connected to mcp_audit.")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.begin() as conn:
            if apply:
                conn.execute(select(func.pg_advisory_xact_lock(84190237)))
                metadata.create_all(conn)
            else:
                from sqlalchemy import inspect

                if not inspect(conn).has_table(versions.name):
                    return {
                        "applied": [],
                        "pending": [p.name for p in sorted(directory.glob("*.sql"))],
                    }
            current = {r.version: r.sha256 for r in conn.execute(select(versions))}
            applied, pending = [], []
            for path in sorted(directory.glob("*.sql")):
                number = int(path.name.split("_", 1)[0])
                script = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(script.encode()).hexdigest()
                if number in current:
                    if current[number] != digest:
                        raise ValueError("An applied audit migration has changed.")
                    applied.append(path.name)
                elif apply:
                    conn.exec_driver_sql(script, execution_options={"no_parameters": True})
                    conn.execute(
                        insert(versions).values(version=number, filename=path.name, sha256=digest)
                    )
                    applied.append(path.name)
                else:
                    pending.append(path.name)
            return {"applied": applied, "pending": pending}
    finally:
        engine.dispose()
