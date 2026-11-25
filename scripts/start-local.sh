#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  --plan)
    exec python3 backend/scripts/verify_all_models.py --plan
    ;;
  --prepare|"") ;;
  *)
    printf 'Usage: bash scripts/start-local.sh [--plan | --prepare]\n' >&2
    exit 2
    ;;
esac

if [[ "${1:-}" != --prepare ]]; then
  docker info >/dev/null
  docker compose version --short >/dev/null
fi

if ! python3 backend/scripts/verify_all_models.py; then
  printf '\nPreparing up to 564 MB of model files, plus pinned source checkouts.\n'
  bash backend/scripts/download_models.sh core
  bash backend/scripts/download_models.sh poc-artifacts
  bash backend/scripts/download_public_assets.sh models
  bash backend/scripts/download_public_assets.sh community-forensics
  bash backend/scripts/download_public_assets.sh poc-artifacts
  python3 backend/scripts/verify_all_models.py
fi

# Exclusive creation preserves every existing .env, including if setup runs twice.
python3 - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
import os

os.umask(0o077)
template = Path(".env.all-models.example").read_text()
for placeholder in (
    "replace-with-a-strong-investigator-password",
    "replace-with-a-different-supervisor-password",
    "replace-with-at-least-32-random-characters",
):
    template = template.replace(placeholder, token_urlsafe(36))
try:
    with Path(".env").open("x") as env_file:
        env_file.write(template)
except FileExistsError:
    pass
else:
    print("Created .env with local sign-in credentials.")
PY

if [[ "${1:-}" == --prepare ]]; then
  exit 0
fi

compose=(docker compose -f docker-compose.yml -f docker-compose.all-models.yml)
"${compose[@]}" config --quiet
docker build -t deeptrace-backend:core ./backend
"${compose[@]}" up -d --build --wait
printf '\nDeepTrace is ready at http://localhost:3000\nSign in using the employee or supervisor credentials in .env.\n'
