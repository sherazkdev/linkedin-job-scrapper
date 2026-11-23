#!/usr/bin/env bash
# Backup jobs + promotion_audit for a Mongo database (no deletes).
set -euo pipefail
DB_NAME="${1:?usage: server_mongo_backup_jobs.sh <db_name>}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR="${BACKUP_ROOT:-/var/www/linkedin-job-scrapper/evidence/mongo_backups}/${DB_NAME}-${STAMP}"
mkdir -p "$OUT_DIR"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongodump \
  -u "$MONGO_USER" -p "$MONGO_PASS" --authenticationDatabase admin \
  --db "$DB_NAME" --collection jobs --out="/data/db/dump-${STAMP}-${DB_NAME}" \
  >/dev/null
docker exec linkedin-scraper-mongodb mongodump \
  -u "$MONGO_USER" -p "$MONGO_PASS" --authenticationDatabase admin \
  --db "$DB_NAME" --collection promotion_audit_batches --out="/data/db/dump-${STAMP}-${DB_NAME}" \
  2>/dev/null || true
docker cp "linkedin-scraper-mongodb:/data/db/dump-${STAMP}-${DB_NAME}" "$OUT_DIR"
MANIFEST="${OUT_DIR}/BACKUP_OK.json"
JOBS_BSON="${OUT_DIR}/dump-${STAMP}-${DB_NAME}/${DB_NAME}/jobs.bson"
if [ ! -f "$JOBS_BSON" ]; then
  echo "BACKUP_VERIFY_FAIL missing jobs.bson" >&2
  exit 1
fi
BYTES=$(wc -c <"$JOBS_BSON")
python3 -c "import json; json.dump({'db':'${DB_NAME}','stamp':'${STAMP}','jobs_bson_bytes':int('${BYTES}'),'ok':True}, open('${MANIFEST}','w'), indent=2)"
echo "BACKUP_OK path=${OUT_DIR} jobs_bson_bytes=${BYTES}"