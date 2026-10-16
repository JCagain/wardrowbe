#!/usr/bin/env bash
# Back up everything that is not in git: the database, the image volume and
# the runtime-edited vocabulary file (spec §8: backup = volume + DB dump).
# Usage: scripts/backup.sh [output-dir]   (default: ~/wardrobe-backups)
set -euo pipefail

cd "$(dirname "$0")/.."
OUT_ROOT="${1:-$HOME/wardrobe-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_ROOT/$STAMP"
mkdir -p "$OUT"

PROJECT="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
VOLUME="${PROJECT}_wardrobe_data"

echo "[1/3] database -> $OUT/db.dump"
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/db.dump"

echo "[2/3] images ($VOLUME) -> $OUT/wardrobe_data.tar.gz"
docker run --rm -v "$VOLUME":/data:ro -v "$OUT":/backup alpine \
  tar czf /backup/wardrobe_data.tar.gz -C /data .

echo "[3/3] vocabulary -> $OUT/garment_vocabulary.json"
cp backend/app/data/garment_vocabulary.json "$OUT/"

git rev-parse HEAD > "$OUT/commit.txt"
docker compose exec -T backend alembic current 2>/dev/null | tail -1 > "$OUT/alembic.txt" || true

# A dump that is empty or a tarball that will not list is not a backup.
test -s "$OUT/db.dump"
tar tzf "$OUT/wardrobe_data.tar.gz" > /dev/null

du -sh "$OUT"/*
echo "done: $OUT"
