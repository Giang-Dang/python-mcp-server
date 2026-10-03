"""Settings (read from .env) and the size profiles (S and M)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Connection settings. Values come from environment variables or the project's .env file."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "shop"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    shop_owner_password: str = ""
    loader_password: str = ""
    mcp_reader_password: str = ""
    mcp_writer_password: str = ""
    mcp_proc_exec_password: str = ""
    shop_scale: str = "S"
    shop_seed: int = 42

    def password_for(self, role: str) -> str:
        if role == self.postgres_user:
            return self.postgres_password
        return getattr(self, f"{role}_password")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@dataclass(frozen=True)
class Scale:
    """Row counts for one size profile. Everything else (child rows) is derived from these."""

    name: str
    tenants: int
    categories_top: int
    categories: int
    suppliers: int
    warehouses: int
    employees: int
    customers: int
    products: int
    orders: int
    carts: int
    inventory_movements: int
    audit_log: int
    price_history: int

    # Fixed ratios that keep ids computable without lookups.
    variants_per_product = 4
    addresses_per_customer = 2  # address 2c-1 is shipping, 2c is billing, for customer c

    @property
    def variants(self) -> int:
        return self.products * self.variants_per_product

    @property
    def addresses(self) -> int:
        return self.customers * self.addresses_per_customer


SCALES: dict[str, Scale] = {
    "S": Scale(
        name="S",
        tenants=5,
        categories_top=10,
        categories=60,
        suppliers=200,
        warehouses=10,
        employees=300,
        customers=50_000,
        products=10_000,
        orders=200_000,
        carts=100_000,
        inventory_movements=800_000,
        audit_log=1_500_000,
        price_history=30_000,
    ),
    "M": Scale(
        name="M",
        tenants=20,
        categories_top=20,
        categories=200,
        suppliers=5_000,
        warehouses=50,
        employees=2_000,
        customers=1_000_000,
        products=100_000,
        orders=5_000_000,
        carts=2_000_000,
        inventory_movements=20_000_000,
        audit_log=30_000_000,
        price_history=400_000,
    ),
}


def get_scale(name: str) -> Scale:
    try:
        return SCALES[name.upper()]
    except KeyError:
        raise ValueError(f"Unknown scale {name!r}; choose one of {sorted(SCALES)}") from None
