#!/usr/bin/env bash
set -euo pipefail
docker run --rm -v linkedin_scraper_linkedin_auth:/data/linkedin alpine ls -la /data/linkedin/
docker run --rm -v linkedin_scraper_linkedin_auth:/data/linkedin python:3.13-alpine python -c "import json,os; p='/data/linkedin/storage_state.json'; print('exists', os.path.isfile(p)); d=json.load(open(p)); print('cookie_count', len(d.get('cookies',[])))"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.linkedin_session status