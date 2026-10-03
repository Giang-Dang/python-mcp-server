import re
from pathlib import Path

import yaml

from mcp_server.core.procedures.domain import TYPES, Parameter, Procedure

NAMES = frozenset(
    (
        "create_order",
        "cancel_order",
        "refund_order",
        "adjust_inventory",
        "update_customer_email",
        "apply_discount",
        "archive_old_orders",
        "recalc_customer_tiers",
        "rebuild_daily_aggregates",
        "purge_abandoned_carts",
    )
)


def load_registry(path: Path) -> dict[str, Procedure]:
    document = yaml.safe_load(path.read_text(encoding="ascii"))
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Unsupported procedure registry version.")
    result = {}
    for raw in document["procedures"]:
        raw = dict(raw)
        raw["parameters"] = tuple(Parameter(**p) for p in raw["parameters"])
        entry = Procedure(**raw)
        if entry.name not in NAMES or entry.name in result:
            raise ValueError("Unreviewed or duplicate procedure.")
        signature = f"shop.{entry.name}(" + ",".join(p.type for p in entry.parameters) + ")"
        if entry.signature != signature or not re.fullmatch("[0-9a-f]{64}", entry.definition_hash):
            raise ValueError("Registry signature or definition hash is invalid.")
        if not entry.effects or not 1 <= entry.timeout_seconds <= 60:
            raise ValueError("Registry effects and bounded timeout are required.")
        archive = entry.name == "archive_old_orders"
        if (entry.role, entry.transaction_mode) != (
            ("mcp_writer", "autocommit_batches") if archive else ("mcp_proc_exec", "atomic")
        ):
            raise ValueError("Unreviewed execution shape.")
        for p in entry.parameters:
            if p.type not in TYPES or not re.fullmatch("p_[a-z_]+", p.name):
                raise ValueError("Invalid registry parameter.")
            if not 1 <= p.max_length <= 1000 or (
                p.minimum is not None and p.maximum is not None and p.minimum > p.maximum
            ):
                raise ValueError("Invalid parameter bounds.")
            if not p.required:
                p.validate(p.default)
        if len({p.name for p in entry.parameters}) != len(entry.parameters):
            raise ValueError("Duplicate registry parameter.")
        controlled = {p.name for p in entry.parameters if p.server_controlled}
        expected = {"create_order": {"p_order_id"}, "purge_abandoned_carts": {"p_deleted"}}.get(
            entry.name, set()
        )
        if controlled != expected:
            raise ValueError("INOUT bookkeeping must remain server-controlled.")
        if archive:
            bounds = {p.name: p.maximum for p in entry.parameters}
            if bounds.get("p_batch_size") != 5000 or bounds.get("p_max_batches") != 10:
                raise ValueError("Archive hard bounds must be 5000 rows and 10 batches.")
        result[entry.name] = entry
    if result.keys() != NAMES:
        raise ValueError("The production registry must contain the ten reviewed procedures.")
    return result
