#!/usr/bin/env bash
set -e

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
    cp .env.example .env
fi

export ENVIRONMENT=development
export DATABASE_URL=
export SUPABASE_DB_URL=
export SUPABASE_URL=
export SUPABASE_PUBLISHABLE_KEY=
export SUPABASE_SECRET_KEY=

exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload