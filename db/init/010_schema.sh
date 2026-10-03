#!/bin/bash
# 010_schema.sh
# The Postgres image only runs files placed directly in /docker-entrypoint-initdb.d, never files in
# sub-folders. The schema lives in its own folder (db/schema, mounted at /db/schema), so this wrapper
# applies those files in name order.
#
# ON_ERROR_STOP makes psql exit non-zero on the first SQL error, which stops initialization instead of
# leaving a half-built schema behind.

set -euo pipefail

for f in /db/schema/*.sql; do
    echo ">>> applying ${f}"
    psql -v ON_ERROR_STOP=1 --no-psqlrc \
        --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
        --file "${f}"
done
