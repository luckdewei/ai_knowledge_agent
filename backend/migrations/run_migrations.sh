#!/usr/bin/env bash
# 按顺序执行 backend/migrations/*.sql
# 用法:
#   ./backend/migrations/run_migrations.sh
#   ./backend/migrations/run_migrations.sh docker   # 通过 pka-postgres 容器执行

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT/backend/migrations"

MODE="${1:-local}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-knowledge_db}"
PGPASSWORD="${PGPASSWORD:-postgres123}"
export PGPASSWORD

if [[ "$MODE" == "docker" ]]; then
  if ! docker ps --format '{{.Names}}' | grep -qx 'pka-postgres'; then
    echo "启动 PostgreSQL 容器..."
    docker compose -f "$ROOT/docker-compose.yml" up -d postgres
    echo "等待数据库就绪..."
    for _ in $(seq 1 30); do
      docker exec pka-postgres pg_isready -U postgres >/dev/null 2>&1 && break
      sleep 1
    done
  fi
fi

run_psql() {
  local file="$1"
  echo ""
  echo ">>> $(basename "$file")"
  if [[ "$MODE" == "docker" ]]; then
    docker exec -i pka-postgres psql -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 <"$file"
  else
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -f "$file"
  fi
}

for f in \
  "$MIGRATIONS_DIR/001_supplement_tables.sql" \
  "$MIGRATIONS_DIR/002_tenant_auth.sql" \
  "$MIGRATIONS_DIR/003_username_global_unique.sql" \
  "$MIGRATIONS_DIR/004_memory_tenant.sql"; do
  run_psql "$f"
done

echo ""
echo ">>> 迁移完成，当前状态："
if [[ "$MODE" == "docker" ]]; then
  docker exec pka-postgres psql -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 'tenants' AS item, COUNT(*)::text FROM tenants
    UNION ALL SELECT 'users', COUNT(*)::text FROM users
    UNION ALL SELECT 'knowledge', COUNT(*)::text FROM knowledge;
    SELECT indexname FROM pg_indexes WHERE tablename = 'users' ORDER BY 1;
  "
else
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 'tenants' AS item, COUNT(*)::text FROM tenants
    UNION ALL SELECT 'users', COUNT(*)::text FROM users
    UNION ALL SELECT 'knowledge', COUNT(*)::text FROM knowledge;
    SELECT indexname FROM pg_indexes WHERE tablename = 'users' ORDER BY 1;
  "
fi
