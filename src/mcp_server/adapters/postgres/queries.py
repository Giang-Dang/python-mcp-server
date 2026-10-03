"""All server-owned catalog and diagnostic SELECTs are SQLAlchemy Core expressions."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    column,
    func,
    select,
    table,
)

from mcp_server.core.errors import Category, GuardError

catalog = MetaData(schema="pg_catalog")
namespace = Table("pg_namespace", catalog, Column("oid", Integer), Column("nspname", String))
relation = Table(
    "pg_class",
    catalog,
    Column("oid", Integer),
    Column("relname", String),
    Column("relnamespace", Integer),
    Column("relkind", String),
    Column("relispartition", Boolean),
    Column("reltuples", Float),
)
attribute = table(
    "pg_attribute",
    *[
        column(n)
        for n in (
            "attrelid",
            "attnum",
            "attname",
            "atttypid",
            "atttypmod",
            "attnotnull",
            "attisdropped",
        )
    ],
    schema="pg_catalog",
)
procedure = table(
    "pg_proc",
    *[column(n) for n in ("oid", "proname", "pronamespace", "prokind")],
    schema="pg_catalog",
)


def tables_query(schema="shop"):
    return (
        select(
            relation.c.relname.label("table"),
            (relation.c.relkind == "p").label("partitioned"),
            func.greatest(relation.c.reltuples, 0).cast(BigInteger).label("approx_rows"),
            func.obj_description(relation.c.oid, "pg_class").label("comment"),
        )
        .join(namespace, namespace.c.oid == relation.c.relnamespace)
        .where(
            namespace.c.nspname == schema,
            relation.c.relkind.in_(("r", "p")),
            relation.c.relispartition.is_(False),
        )
        .order_by(relation.c.relname)
    )


def describe_query(name, schema="shop"):
    return (
        select(
            attribute.c.attname.label("name"),
            func.format_type(attribute.c.atttypid, attribute.c.atttypmod).label("type"),
            attribute.c.attnotnull.label("not_null"),
            func.col_description(relation.c.oid, attribute.c.attnum).label("comment"),
        )
        .select_from(
            relation.join(namespace, namespace.c.oid == relation.c.relnamespace).join(
                attribute, attribute.c.attrelid == relation.c.oid
            )
        )
        .where(
            namespace.c.nspname == schema,
            relation.c.relname == name,
            relation.c.relkind.in_(("r", "p")),
            attribute.c.attnum > 0,
            attribute.c.attisdropped.is_(False),
        )
        .order_by(attribute.c.attnum)
    )


def definition_query(signature):
    return select(func.pg_get_functiondef(func.to_regprocedure(signature)))


def definitions_query(schema="shop"):
    return (
        select(
            procedure.c.proname.label("name"),
            func.pg_get_function_identity_arguments(procedure.c.oid).label("arguments"),
            func.pg_get_functiondef(procedure.c.oid).label("definition"),
        )
        .select_from(procedure.join(namespace, namespace.c.oid == procedure.c.pronamespace))
        .where(namespace.c.nspname == schema, procedure.c.prokind == "p")
        .order_by(procedure.c.proname)
    )


def diagnostics_query(kind, schema="shop"):
    if kind == "query_statistics":
        t = table(
            "pg_stat_statements",
            *[
                column(n)
                for n in (
                    "queryid",
                    "calls",
                    "total_exec_time",
                    "mean_exec_time",
                    "rows",
                    "query",
                    "dbid",
                )
            ],
            schema="public",
        )
        return (
            select(t)
            .where(
                t.c.dbid
                == select(column("oid"))
                .select_from(
                    table("pg_database", column("oid"), column("datname"), schema="pg_catalog")
                )
                .where(column("datname") == func.current_database())
                .scalar_subquery()
            )
            .order_by(t.c.total_exec_time.desc())
        )
    if kind == "locks":
        t = table(
            "pg_locks",
            *[column(n) for n in ("pid", "locktype", "relation", "mode", "granted")],
            schema="pg_catalog",
        )
        return select(t)
    if kind == "table_sizes":
        return (
            select(
                relation.c.relname.label("table"),
                func.pg_total_relation_size(relation.c.oid).label("total_bytes"),
                func.pg_relation_size(relation.c.oid).label("table_bytes"),
            )
            .join(namespace, namespace.c.oid == relation.c.relnamespace)
            .where(
                namespace.c.nspname == schema,
                relation.c.relkind.in_(("r", "p")),
                relation.c.relispartition.is_(False),
            )
            .order_by(func.pg_total_relation_size(relation.c.oid).desc())
        )
    if kind == "table_health":
        t = table(
            "pg_stat_user_tables",
            *[
                column(n)
                for n in (
                    "schemaname",
                    "relname",
                    "n_live_tup",
                    "n_dead_tup",
                    "last_autovacuum",
                    "last_autoanalyze",
                    "seq_scan",
                    "idx_scan",
                )
            ],
            schema="pg_catalog",
        )
        return select(t).where(t.c.schemaname == schema).order_by(t.c.n_dead_tup.desc())
    raise GuardError(Category.ARGUMENTS, "Unknown diagnostic report.")
