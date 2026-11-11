#!/bin/sh
set -e

# Remap the container user/group to match the host so mounted volumes stay writable.
if [ -n "$USER_ID" ]; then
  usermod -u "$USER_ID" eventscraper
fi

if [ -n "$GROUP_ID" ]; then
  groupmod -g "$GROUP_ID" eventg
fi

# exec so Python becomes PID 1 and receives SIGTERM from `docker stop`.
if [ "$(id -u)" -eq 0 ]; then
  chown -R eventscraper:eventg /app
  # Gosu https://github.com/tianon/gosu
  exec gosu eventscraper:eventg /app/.venv/bin/python /app/calendar_event_engine/Runner.py
else
  exec /app/.venv/bin/python /app/calendar_event_engine/Runner.py
fi
