#!/usr/bin/env bash
set -uo pipefail

trap 'kill 0' TERM INT

python -m mcp_server.server &
python -m backend &

wait -n
exit $?
