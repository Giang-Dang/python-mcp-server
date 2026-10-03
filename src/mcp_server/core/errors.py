"""Stable public failures, without driver messages or credentials."""

from enum import StrEnum


class Category(StrEnum):
    AUTHENTICATION = "authentication"
    POLICY = "policy_rejection"
    ARGUMENTS = "invalid_arguments"
    LIMIT = "limits"
    REGISTRY = "registry_mismatch"
    AUDIT = "audit_unavailability"
    DATABASE = "database_failure"
    UNCERTAIN = "uncertain_completion"


class GuardError(Exception):
    def __init__(self, category: Category, message: str, outcome: str = "rejected"):
        super().__init__(message)
        self.category, self.outcome = category, outcome
