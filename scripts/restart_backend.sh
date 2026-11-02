#!/usr/bin/env bash
# Restart the dev API (with in-process worker) using a pidfile.
PIDF=/tmp/nexora-backend.pid
[ -f $PIDF ] && kill "$(cat $PIDF)" 2>/dev/null && sleep 1
cd "$(dirname "$0")/../backend"
SUPER_ADMIN_EMAILS=${SUPER_ADMIN_EMAILS:-admin@example.com} nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/nexora-backend.log 2>&1 &
echo $! > $PIDF
