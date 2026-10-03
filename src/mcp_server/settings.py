"""Runtime-only configuration. Migration credentials have no field here."""

from dataclasses import fields
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp_server.core.sql_access.domain import Limits

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHOPMCP_", env_file=ROOT / ".env.mcp", extra="ignore"
    )
    auth0_domain: str
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5433, ge=1, le=65535)
    shop_database: str = "shop"
    audit_database: str = "mcp_audit"
    reader_password: SecretStr
    writer_password: SecretStr
    procedure_password: SecretStr
    monitor_password: SecretStr
    audit_password: SecretStr
    schema_name: str = "shop"
    tenant_id: int = Field(default=1, ge=1)
    registry_path: Path = ROOT / "config" / "procedures.yaml"
    request_bytes: int = Field(default=65536, ge=1024, le=65536)
    result_rows: int = Field(default=1000, ge=1, le=10000)
    result_bytes: int = Field(default=1048576, ge=256, le=16777216)
    read_seconds: int = Field(default=15, ge=1, le=300)
    write_seconds: int = Field(default=30, ge=1, le=300)
    procedure_seconds: int = Field(default=60, ge=1, le=600)
    affected_rows: int = Field(default=1000, ge=1, le=10000)
    approval_seconds: int = Field(default=300, ge=1, le=300)
    plan_cost: float = Field(default=1000000, gt=0, allow_inf_nan=False)

    @field_validator("host")
    @classmethod
    def loopback(cls, value):
        if value != "127.0.0.1":
            raise ValueError("The supported runtime binds to 127.0.0.1.")
        return value

    @field_validator("schema_name")
    @classmethod
    def shop_schema(cls, value):
        if value != "shop":
            raise ValueError("The reviewed fixture and registry use the shop schema.")
        return value

    @field_validator("auth0_domain")
    @classmethod
    def domain(cls, value):
        import re

        if (
            not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", value)
            or "." not in value
        ):
            raise ValueError("Provide the Auth0 domain only, without a scheme or path.")
        return value

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    @property
    def resource_url(self):
        return self.base_url + "/mcp"

    @property
    def issuer(self):
        return f"https://{self.auth0_domain}/"

    @property
    def limits(self):
        return Limits(**{f.name: getattr(self, f.name) for f in fields(Limits)})

    def password_for(self, role):
        field = {
            "mcp_reader": "reader_password",
            "mcp_writer": "writer_password",
            "mcp_proc_exec": "procedure_password",
            "mcp_monitor": "monitor_password",
            "mcp_audit_runtime": "audit_password",
        }[role]
        return getattr(self, field).get_secret_value()
