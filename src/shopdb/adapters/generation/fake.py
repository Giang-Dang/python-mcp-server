"""Faker helpers: cached instances that are re-seeded for every chunk.

Creating a Faker instance takes a few hundred milliseconds, so each process keeps one per locale.
Re-seeding at the start of every chunk makes the output depend only on (seed, chunk), not on which
worker handled the chunk or in what order.
"""

from __future__ import annotations

import re

from faker import Faker

from shopdb.core.dataset.domain import hash3

LOCALES = {"US": "en_US", "GB": "en_GB", "DE": "de_DE", "FR": "fr_FR", "CA": "en_CA", "AU": "en_AU"}

_CACHE: dict[str, Faker] = {}


def faker_for(locale: str, seed: int, salt: int, chunk: int) -> Faker:
    fake = _CACHE.get(locale)
    if fake is None:
        fake = _CACHE[locale] = Faker(locale)
    fake.seed_instance(hash3(seed, salt, chunk) & 0xFFFFFFFF)
    return fake


def faker_by_country(seed: int, salt: int, chunk: int) -> dict[str, Faker]:
    return {code: faker_for(locale, seed, salt, chunk) for code, locale in LOCALES.items()}


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """ASCII-only lowercase slug: 'O'Brien' -> 'obrien'. Non-ASCII letters are dropped."""
    return _NON_ALNUM.sub("", text.lower())
