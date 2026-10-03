"""Database tests require opt-in to our dedicated port; never fall back to .env."""

import os

import pytest

DATABASE_MODULES = {
    "test_seed_integrity.py",
    "test_planted.py",
    "test_docgen.py",
    "test_guarded_integration.py",
}


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires the isolated PostgreSQL instance")
    if os.environ.get("SHOP_TEST_DATABASE") == "isolated":
        from support import seed_settings

        from shopdb.settings import get_settings

        selected = seed_settings()
        for key, value in selected.model_dump().items():
            os.environ[key.upper()] = str(value)
        get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.path.name in DATABASE_MODULES:
            item.add_marker(pytest.mark.integration)
        if os.environ.get("SHOP_TEST_DATABASE") == "isolated":
            continue
        if item.path.name in DATABASE_MODULES or "integration" in item.keywords:
            item.add_marker(
                pytest.mark.skip(reason="set SHOP_TEST_DATABASE=isolated; uses port 55439 only")
            )
