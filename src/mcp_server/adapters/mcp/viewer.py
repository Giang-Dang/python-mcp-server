"""Packaged MCP App. No DB access and no remote assets."""

from importlib.resources import files

from fastmcp.apps.config import UI_MIME_TYPE, AppConfig, ResourceCSP, ResourcePermissions
from fastmcp.exceptions import ResourceError
from fastmcp.resources.base import ResourceContent, ResourceResult

VIEWER_URI = "ui://shop/query-plan-viewer.html"


def register_viewer(mcp):
    @mcp.resource(
        VIEWER_URI,
        name="query_plan_viewer",
        description="Interactive estimates-only PostgreSQL plan tree and node details.",
        mime_type=UI_MIME_TYPE,
        app=AppConfig(
            csp=ResourceCSP(
                connect_domains=[], resource_domains=[], frame_domains=[], base_uri_domains=[]
            ),
            permissions=ResourcePermissions(),
        ),
    )
    def query_plan_viewer() -> ResourceResult:
        try:
            html = (
                files("mcp_server")
                .joinpath("adapters/mcp/query_plan_viewer/viewer.html")
                .read_text(encoding="ascii")
            )
        except (OSError, UnicodeError):
            raise ResourceError(
                "Query plan viewer asset is unavailable; rebuild the frontend."
            ) from None
        return ResourceResult([ResourceContent(html, mime_type=UI_MIME_TYPE)])
