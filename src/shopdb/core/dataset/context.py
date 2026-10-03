"""Read-only data every worker process needs. Built once by the main process, sent to each worker once."""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field

from .scales import Scale


@dataclass
class SeedContext:
    scale: Scale
    seed: int
    order_offsets: list[dict[str, int]]  # first child-table ids for each order chunk
    totals: dict[str, int]  # final row counts of the order child tables
    order_counts: array  # orders per customer id (index 0 unused)
    _prices: list[int] = field(default_factory=list, repr=False)

    def product_prices(self) -> list[int]:
        """Base price in cents for every product id (index 0 unused); computed lazily, once per process."""
        if not self._prices:
            from .domain import price_cents

            self._prices = [0] + [
                price_cents(p, self.seed) for p in range(1, self.scale.products + 1)
            ]
        return self._prices
