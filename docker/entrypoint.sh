#!/bin/bash
set -e

if [ "${AUTO_LAUNCH_CLAUDE:-}" = "1" ]; then
  exec claude "$@"
fi

exec "$@"
