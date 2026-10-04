"""Published output contracts. Framework types stay outside Core."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanNode(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    node_type: str | None = Field(default=None, alias="Node Type")
    total_cost: float | None = Field(default=None, alias="Total Cost")
    startup_cost: float | None = Field(default=None, alias="Startup Cost")
    plan_rows: int | None = Field(default=None, alias="Plan Rows")
    plan_width: int | None = Field(default=None, alias="Plan Width")
    relation_name: str | None = Field(default=None, alias="Relation Name")
    plans: list["PlanNode"] = Field(default_factory=list, alias="Plans")


class ExplainData(BaseModel):
    plan: PlanNode
    total_cost_estimate: float
    rows_estimate: int
    estimates_only: Literal[True]


class PublicError(BaseModel):
    category: str
    message: str


class Envelope(BaseModel):
    operation_id: str
    outcome: str
    audit_status: Literal["recorded", "unavailable", "not_recorded"]
    error: PublicError | None = None
    retry_safe: bool | None = None


class ExplainResponse(Envelope):
    data: ExplainData | None


class TabularData(BaseModel):
    columns: list[str]
    returned_rows: int
    truncated: bool
    truncation_reason: Literal["rows", "bytes"] | None
    result_bytes: int
    byte_scope: Literal["JSON columns and rows"]


class QueryStatistics(TabularData):
    kind: Literal["query_statistics"]
    rows: list[tuple[int, int, float, float, int, str | None, int]] = Field(
        description="queryid, calls, total_exec_time (ms), mean_exec_time (ms), rows, query, dbid"
    )


class Locks(TabularData):
    kind: Literal["locks"]
    rows: list[tuple[int | None, str, int | None, str, bool]] = Field(
        description="pid (nullable), locktype, relation OID (nullable), mode, granted"
    )


class TableSizes(TabularData):
    kind: Literal["table_sizes"]
    rows: list[tuple[str, int, int]] = Field(description="table, total_bytes, table_bytes")


class TableHealth(TabularData):
    kind: Literal["table_health"]
    rows: list[tuple[str, str, int, int, str | None, str | None, int, int | None]] = Field(
        description="schemaname, relname, n_live_tup, n_dead_tup, last_autovacuum (ISO/null), last_autoanalyze (ISO/null), seq_scan, idx_scan (nullable)"
    )


DiagnosticData = Annotated[
    QueryStatistics | Locks | TableSizes | TableHealth, Field(discriminator="kind")
]


class DiagnosticsResponse(Envelope):
    data: DiagnosticData | None
