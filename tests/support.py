"""Explicit isolated instance configuration; never load the project's .env."""

from shopdb.settings import Settings

TEST_PORT = 55439


def server_settings(**overrides):
    from mcp_server.settings import Settings as ServerSettings

    values = {
        "_env_file": None,
        "auth0_domain": "test.auth0.com",
        "postgres_host": "127.0.0.1",
        "postgres_port": TEST_PORT,
        "shop_database": "shop",
        "audit_database": "mcp_audit",
        "reader_password": "test_reader",
        "writer_password": "test_writer",
        "procedure_password": "test_proc",
        "monitor_password": "test_monitor",
        "audit_password": "test_audit",
    }
    return ServerSettings(**(values | overrides))


def seed_settings() -> Settings:
    return Settings(
        _env_file=None,
        postgres_host="127.0.0.1",
        postgres_port=TEST_PORT,
        postgres_db="shop",
        postgres_user="postgres",
        postgres_password="test_admin",
        shop_owner_password="test_owner",
        loader_password="test_loader",
        mcp_reader_password="test_reader",
        mcp_writer_password="test_writer",
        mcp_proc_exec_password="test_proc",
        shop_scale="S",
        shop_seed=42,
    )
