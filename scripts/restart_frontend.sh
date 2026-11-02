#!/usr/bin/env bash
# Restart the production Next.js server using a pidfile (avoids pattern-matching kills).
PIDF=/tmp/nexora-frontend.pid
[ -f $PIDF ] && kill "$(cat $PIDF)" 2>/dev/null && sleep 1
cd "$(dirname "$0")/../frontend"
NEXT_TELEMETRY_DISABLED=1 nohup node node_modules/next/dist/bin/next start -p 3000 > /tmp/nexora-frontend.log 2>&1 &
echo $! > $PIDF
