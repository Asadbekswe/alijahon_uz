#!/bin/sh
set -e

# Apply migrations before the main process starts (database health is guaranteed by compose depends_on).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${RUN_SEED:-0}" = "1" ]; then
    python manage.py seed_dev_data
fi

exec "$@"
