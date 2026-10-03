"""Positive allowlists: parser additions are rejected until reviewed."""

from mcp_server.core.errors import Category, GuardError

from .domain import Analysis

NODES = frozenset(
    [
        "Select",
        "Union",
        "Intersect",
        "Except",
        "Subquery",
        "CTE",
        "With",
        "From",
        "Join",
        "Table",
        "TableAlias",
        "Identifier",
        "Column",
        "Star",
        "Literal",
        "Boolean",
        "Null",
        "Paren",
        "Alias",
        "Distinct",
        "Where",
        "Group",
        "Having",
        "Order",
        "Ordered",
        "Limit",
        "Offset",
        "And",
        "Or",
        "Not",
        "EQ",
        "NEQ",
        "GT",
        "GTE",
        "LT",
        "LTE",
        "Is",
        "In",
        "Between",
        "Like",
        "ILike",
        "Add",
        "Sub",
        "Mul",
        "Div",
        "Mod",
        "Neg",
        "Tuple",
        "Case",
        "If",
        "Cast",
        "TryCast",
        "DataType",
        "DataTypeParam",
        "Filter",
        "Window",
        "WindowSpec",
        "Partition",
        "By",
        "Insert",
        "Update",
        "Delete",
        "Schema",
        "Values",
        "Returning",
        "Count",
        "Sum",
        "Avg",
        "Min",
        "Max",
        "Abs",
        "Round",
        "Ceil",
        "Floor",
        "Lower",
        "Upper",
        "Length",
        "Trim",
        "Coalesce",
        "Nullif",
        "Greatest",
        "Least",
        "Extract",
        "DateTrunc",
        "CurrentDate",
        "CurrentTimestamp",
    ]
)
FUNCTIONS = frozenset(
    [
        "And",
        "Or",
        "Count",
        "Sum",
        "Avg",
        "Min",
        "Max",
        "Abs",
        "Round",
        "Ceil",
        "Floor",
        "Lower",
        "Upper",
        "Length",
        "Trim",
        "Coalesce",
        "Nullif",
        "Greatest",
        "Least",
        "Extract",
        "DateTrunc",
        "CurrentDate",
        "CurrentTimestamp",
        "Case",
        "If",
        "Cast",
        "TryCast",
    ]
)


def authorize(analysis: Analysis, tool: str, schema: str = "shop") -> Analysis:
    if analysis.violations:
        raise GuardError(Category.POLICY, "; ".join(analysis.violations))
    if analysis.node_types - NODES or analysis.functions - FUNCTIONS:
        raise GuardError(Category.POLICY, "SQL contains an unreviewed expression or function.")
    if any(s != schema for s, _ in analysis.tables):
        raise GuardError(Category.POLICY, "Use schema-qualified shop tables only.")
    if tool in ("query", "explain") and analysis.kind != "read":
        raise GuardError(Category.POLICY, "This tool accepts read SQL only.")
    if tool == "execute" and analysis.kind not in ("insert", "update", "delete"):
        raise GuardError(Category.POLICY, "execute accepts INSERT, UPDATE, or DELETE only.")
    if analysis.kind in ("update", "delete") and not analysis.has_where:
        raise GuardError(Category.POLICY, "UPDATE and DELETE require WHERE.")
    return analysis
