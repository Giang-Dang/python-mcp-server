from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from mcp_server.core.access_control.application import fingerprint
from mcp_server.core.errors import Category, GuardError

TYPES = {"bigint", "integer", "smallint", "numeric", "text", "date", "bigint[]", "integer[]"}


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    required: bool = True
    default: object = None
    minimum: float | None = None
    maximum: float | None = None
    max_length: int = 256
    nullable: bool = False
    server_controlled: bool = False

    def validate(self, value: object) -> object:
        def invalid():
            raise GuardError(Category.ARGUMENTS, f"Invalid value for {self.name}.")

        if value is None:
            if self.nullable:
                return None
            invalid()
        if self.type.endswith("[]"):
            if not isinstance(value, list) or not 1 <= len(value) <= self.max_length:
                invalid()
            scalar = Parameter(
                self.name, self.type[:-2], minimum=self.minimum, maximum=self.maximum
            )
            return [scalar.validate(v) for v in value]
        if self.type in ("bigint", "integer", "smallint"):
            if type(value) is not int:
                invalid()
            numeric = value
        elif self.type == "numeric":
            if type(value) not in (int, float, str):
                invalid()
            try:
                numeric = Decimal(str(value))
                if not numeric.is_finite():
                    invalid()
            except InvalidOperation:
                invalid()
        elif self.type == "date":
            if not isinstance(value, str):
                invalid()
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                invalid()
        elif self.type == "text":
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= self.max_length
                or "\x00" in value
            ):
                invalid()
            return value
        else:
            invalid()
        if (self.minimum is not None and numeric < Decimal(str(self.minimum))) or (
            self.maximum is not None and numeric > Decimal(str(self.maximum))
        ):
            invalid()
        return str(numeric) if self.type == "numeric" else numeric


@dataclass(frozen=True)
class Procedure:
    name: str
    signature: str
    definition_hash: str
    parameters: tuple[Parameter, ...]
    effects: str
    timeout_seconds: int
    role: str
    transaction_mode: str

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    def bind(self, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            raise GuardError(Category.ARGUMENTS, "Procedure arguments must be an object.")
        allowed = {p.name for p in self.parameters if not p.server_controlled}
        if arguments.keys() - allowed:
            raise GuardError(Category.ARGUMENTS, "Unknown or server-controlled procedure argument.")
        result = {}
        for parameter in self.parameters:
            if (
                parameter.required
                and parameter.name not in arguments
                and not parameter.server_controlled
            ):
                raise GuardError(Category.ARGUMENTS, f"Missing argument {parameter.name}.")
            value = (
                parameter.default
                if parameter.server_controlled
                else arguments.get(parameter.name, parameter.default)
            )
            result[parameter.name] = parameter.validate(value)
        if self.name == "create_order" and len(result["p_variant_ids"]) != len(
            result["p_quantities"]
        ):
            raise GuardError(
                Category.ARGUMENTS, "Variant and quantity arrays must have equal lengths."
            )
        return result

    def public(self):
        return asdict(self)

    def check_definition(self, definition_hash):
        if definition_hash != self.definition_hash:
            raise GuardError(
                Category.REGISTRY, "Procedure definition differs from the reviewed registry."
            )
