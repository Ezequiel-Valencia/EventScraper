#!/bin/sh

# Check if the USER_ID environment variable is set
if [ -n "$USER_ID" ]; then
  usermod -u $USER_ID eventscraper
fi

# Gosu https://github.com/tianon/gosu
if [ -n "$GROUP_ID" ]; then
  groupmod -g $GROUP_ID eventg
fi

chown -R eventscraper:eventg /app

if [ "$(id -u)" -eq 0 ]; then
  gosu eventscraper:eventg poetry run python /app/calendar_event_engine/Runner.py
else
  poetry run python /app/calendar_event_engine/Runner.py
fi

