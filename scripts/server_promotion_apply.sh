#!/usr/bin/env bash
# One-shot approved promotion apply (caller must have explicit approval).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
BACKUP_ARG="${1:-}"

echo "STEP isolation"
docker exec linkedin-scraper-api printenv MONGO_DB_NAME | grep -qx global_jobs
docker exec linkedin-scraper-api-pilot printenv MONGO_DB_NAME | grep -qx global_jobs_pilot
docker exec linkedin-scraper-api-pilot printenv PROMOTION_TARGET_MONGO_DB_NAME | grep -qx global_jobs
test "$(docker ps --format '{{.Names}}' | grep -c linkedin-scraper-beat || true)" -eq 0

last_json_from() {
  docker exec linkedin-scraper-api-pilot "$@" 2>/dev/null | python3 -c "
import sys, json
buf = sys.stdin.read()
dec = json.JSONDecoder()
idx = 0
last = None
while idx < len(buf):
    while idx < len(buf) and buf[idx] not in '{[':
        idx += 1
    if idx >= len(buf):
        break
    try:
        obj, end = dec.raw_decode(buf, idx)
        last = obj
        idx = end
    except json.JSONDecodeError:
        idx += 1
if last is None:
    raise SystemExit('no_json_in_cli_output')
print(json.dumps(last))
"
}

echo "STEP pre_apply_safety"
bash scripts/server_promotion_safety.sh

VALIDATION_JSON=$(last_json_from python -m app.cli.promote_pilot validate)
python3 -c "import json,sys; r=json.loads(sys.argv[1]); sys.exit(0 if r.get('validation_ok') and r.get('eligible_count')==80 else 2)" "$VALIDATION_JSON"
echo "VALIDATE_OK eligible=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['eligible_count'])" "$VALIDATION_JSON")"

DRY_JSON=$(last_json_from python -m app.cli.promote_pilot dry-run)
python3 -c "import json,sys; r=json.loads(sys.argv[1]); ok=r.get('dry_run_would_create')==80 and r.get('dry_run_would_update')==0 and r.get('validation',{}).get('validation_ok'); sys.exit(0 if ok else 2)" "$DRY_JSON"
echo "DRY_RUN_OK create=$(python3 -c "import json,sys; r=json.loads(sys.argv[1]); print(r['dry_run_would_create'])" "$DRY_JSON")"

if [ -n "$BACKUP_ARG" ]; then
  BACKUP_PATH="$BACKUP_ARG"
else
  BACKUP_JSON=$(last_json_from python -m app.cli.promote_pilot backup)
  BACKUP_PATH=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['backup_path'])" "$BACKUP_JSON")
fi
test -f "$BACKUP_PATH"
python3 -c "import json,pathlib; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); assert len(d.get('pilot_documents') or [])==80; print('BACKUP_VERIFIED', p)" "$BACKUP_PATH"

echo "STEP apply batch"
APPLY_JSON=$(docker exec -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true linkedin-scraper-api-pilot \
  python -m app.cli.promote_pilot apply --backup "$BACKUP_PATH")
echo "$APPLY_JSON"

BATCH_ID=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['batch_id'])" "$APPLY_JSON")
echo "PROMOTION_BATCH_ID=$BATCH_ID"
echo "BACKUP_PATH=$BACKUP_PATH"

echo "STEP post_counts"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const prod=db.getSiblingDB('global_jobs');
const pilot=db.getSiblingDB('global_jobs_pilot');
const dayAgo=new Date(Date.now()-24*3600*1000);
const verified={source:'linkedin',data_provenance:'live_api_verified',status:'active'};
printjson({
  pilot_linkedin_verified: pilot.jobs.countDocuments(verified),
  production_linkedin_verified: prod.jobs.countDocuments(verified),
  production_with_batch: prod.jobs.countDocuments({promotion_batch_id:'${BATCH_ID}'}),
  posted_last_24h_production: prod.jobs.countDocuments({...verified,posted_at:{\$gte:dayAgo}}),
  audit: prod.promotion_audit_batches.findOne({batch_id:'${BATCH_ID}'},{batch_id:1,created:1,updated:1,applied_at:1})
});
"

echo "STEP reset_apply_flag"
if grep -q '^ALLOW_PILOT_TO_PRODUCTION_PROMOTION=' .env 2>/dev/null; then
  sed -i 's/^ALLOW_PILOT_TO_PRODUCTION_PROMOTION=.*/ALLOW_PILOT_TO_PRODUCTION_PROMOTION=false/' .env
else
  echo 'ALLOW_PILOT_TO_PRODUCTION_PROMOTION=false' >>.env
fi
docker exec linkedin-scraper-api-pilot printenv ALLOW_PILOT_TO_PRODUCTION_PROMOTION 2>/dev/null | grep -qx false \
  || echo "NOTE apply_flag_set_via_env_file_only"

echo "STEP public_api_smoke"
if [ -f evidence/publication_readiness/post_promotion_api_verify.sh ]; then
  bash evidence/publication_readiness/post_promotion_api_verify.sh
fi

echo "PROMOTION_APPLY_OK batch=${BATCH_ID}"