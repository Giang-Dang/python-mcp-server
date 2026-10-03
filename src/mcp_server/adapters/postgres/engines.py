from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def make_engine(settings, role, *, dedicated=False):
    database = settings.audit_database if role == "mcp_audit_runtime" else settings.shop_database
    if settings.audit_database == settings.shop_database:
        raise ValueError("Audit storage must use a separate database.")
    url = URL.create(
        "postgresql+psycopg",
        username=role,
        password=settings.password_for(role),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=database,
    )
    options = {"poolclass": NullPool} if dedicated else {"pool_size": 3, "max_overflow": 2}
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args={"connect_timeout": 5, "options": "-c search_path=pg_catalog"},
        **options,
    )
