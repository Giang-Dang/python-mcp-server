"""Official Skills extension, backed by an immutable packaged two-file snapshot."""

import hashlib
from importlib.resources import files

import yaml
from fastmcp.server.extensions import MethodBinding, ServerExtension
from fastmcp.utilities.pagination import paginate_sequence
from mcp.shared.exceptions import MCPError
from mcp_types import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    CacheableResult,
    PaginatedRequestParams,
    RequestParams,
)

EXTENSION = "io.modelcontextprotocol/skills"
ROOT_URI = "skill://investigate-slow-query/"
SKILL_URI = ROOT_URI + "SKILL.md"


class GetSkillParams(RequestParams):
    uri: str


class ListSkillsResult(CacheableResult):
    skills: list[dict]
    next_cursor: str | None = None


class GetSkillResult(CacheableResult):
    skill: dict


class SkillsExtension(ServerExtension):
    identifier = EXTENSION

    def __init__(self, identity, page_size):
        self.identity, self.page_size = identity, page_size
        root = files("mcp_server").joinpath("adapters/mcp/skills/investigate-slow-query")
        self.contents = {
            ROOT_URI + path: root.joinpath(path).read_bytes()
            for path in ("SKILL.md", "references/checklist.md")
        }
        frontmatter = yaml.safe_load(self.contents[SKILL_URI].decode("ascii").split("---", 2)[1])
        self.entry = {
            "uri": SKILL_URI,
            "frontmatter": frontmatter,
            "resources": [
                {
                    "uri": uri,
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
                for uri, content in self.contents.items()
            ],
        }

    def settings(self):
        return {"directoryRead": False}

    def methods(self):
        versions = frozenset({"2026-07-28"})
        return (
            MethodBinding("skills/list", PaginatedRequestParams, self.list, versions),
            MethodBinding("skills/get", GetSkillParams, self.get, versions),
        )

    def require_client(self, ctx):
        self.identity()
        if self.client_settings(ctx) is None:
            raise MCPError(
                code=METHOD_NOT_FOUND, message="Skills extension was not enabled by this client."
            )

    async def list(self, ctx, params):
        self.require_client(ctx)
        try:
            entries, cursor = paginate_sequence(
                [self.entry], params.cursor if params else None, self.page_size
            )
        except ValueError:
            raise MCPError(code=INVALID_PARAMS, message="Invalid skills cursor.") from None
        return ListSkillsResult(result_type="complete", skills=entries, next_cursor=cursor)

    async def get(self, ctx, params):
        self.require_client(ctx)
        if params.uri != SKILL_URI:
            raise MCPError(code=INVALID_PARAMS, message="Unknown skill URI.")
        return GetSkillResult(result_type="complete", skill=self.entry)

    def register_files(self, mcp):
        def reader(content):
            def read() -> str:
                return content.decode("ascii")

            return read

        for uri, content in self.contents.items():
            # Close over the immutable bytes, never resolve a client-controlled path.
            entry_file = uri == SKILL_URI
            mcp.resource(
                uri,
                name=self.entry["frontmatter"]["name"] if entry_file else "slow_query_checklist",
                description=self.entry["frontmatter"]["description"]
                if entry_file
                else "Evidence checklist for investigating a slow query.",
                mime_type="text/markdown",
            )(reader(content))
