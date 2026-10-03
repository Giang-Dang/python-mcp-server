"""Supported entry point: shopmcp serve (authenticated Streamable HTTP)."""

from mcp_server.bootstrap import create_server

__all__ = ["create_server"]


def main():
    from mcp_server.cli import app

    app()


if __name__ == "__main__":
    main()
