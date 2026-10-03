# CLAUDE.md

## Purpose

This repo is a learning project with two parts:

1. **`shop` database**: a realistic Postgres 17 e-commerce database (S ~25 tables / ~500 MB,
   M ~60 tables / ~8-10 GB) with triggers, stored procedures and deliberately planted performance
   problems. It runs in Docker and is filled by a Python seeder.
2. **MCP server** (next phase): a "guarded SQL" server built with FastMCP. It classifies SQL as
   read or mutate, asks the human before mutations (MCP elicitation), and calls only allowlisted
   stored procedures.

The plan lives in `C:\Users\dangv\.claude\plans\agreed-create-plan-to-atomic-pike.md`.

## Layout

- `db/init/` extensions and roles; `db/schema/` tables, partitions, views, RLS (run on first container start)
- `db/post_load/` indexes, triggers, functions, procedures (applied after seeding)
- `db/workload/` pgbench scripts; `db/observability/` diagnostic SQL
- `src/shopdb/` seeder and CLI (`poetry run shopdb ...`); `src/mcp_server/` MCP server
- `tests/` pytest smoke tests; `docs/` documentation

## Commands

```powershell
poetry install                         # create .venv and install dependencies
docker compose up -d --wait           # start Postgres (needs Docker Desktop running)
poetry run shopdb seed --scale S      # load data (S default, M for the big profile)
poetry run shopdb verify              # row counts and FK integrity
poetry run pytest                     # smoke tests
poetry run ruff check . ; poetry run ruff format .
```

Poetry is installed with `uv tool install poetry`; its executable is in `~/.local/bin`
(add it to PATH with `uv tool update-shell` if `poetry` is not found).
Postgres client tools are not on the host: use `docker compose exec db psql -U postgres -d shop`.

## Conventions

- ASCII only in source, SQL and docs. Never use the en-dash U+2013 or other look-alikes of ASCII
  punctuation; use `-` (including date ranges).
- SQL: schema-qualified names (`shop.orders`), snake_case, numbered files that run in order,
  `COMMENT ON` for every table and important column (the data dictionary is generated from them).
- Python 3.12+, ruff formatting (line length 100), type hints.
- Seed data must be deterministic: fixed seeds, no wall-clock dependence.

## Safety rules

- Ask before `docker compose down -v`, `shopdb reset` or anything else that destroys the data volume.
- The planted performance problems (P01-P12 in `docs/planted-problems.md`) are intentional.
  Do not "fix" them with extra indexes or rewrites unless asked.
- Default scale is S. Do not start an M seed (hours, 10-15 GB) without asking.
- Never commit `.env`. Do not run mutating SQL against the database without the user's approval.

## Documentation rule (important)

The user is learning from this project. Whenever you run a setup or build step:

1. Say in the chat reply why the step is being done.
2. In the same turn, append a numbered section to `docs/setup-guide.md` with: goal and why
   (including alternatives rejected), exact commands, what each command does and why, files
   created, real expected output, troubleshooting (errors actually hit), and concepts with links.
3. Record failures and their fixes honestly. A step is not done until its section exists.

## Next phase

Guarded SQL MCP server: see `docs/roadmap.md` (written in the final documentation step).
