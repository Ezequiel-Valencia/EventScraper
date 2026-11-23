# EventScraper

A project dedicated to scrapping events and posting them on
different platforms for searching. Unbinding posted events from any single platform to help illuminate what is locally happening.

Can be imported as a library in a python script or used
directly through a docker container.

## Docker (Recommended Method)
#### [Docker Image](https://hub.docker.com/repository/docker/avocadomoon/event-scraper/general)
#### Env Variables
Mobilizon Related Variables:
- MOBILIZON_ENDPOINT: Graphql endpoint for your mobilizon instance

- MOBILIZON_EMAIL: User email

- MOBILIZON_PASSWORD: User password

OS Related Variables:
- USER_ID: User process ID for running the application

- GROUP_ID: Group process ID for running the application

Misc:
- RUNNER_SUBMISSION_JSON_PATH: Remote submission file that tells where to publish and what group packages to use for sources.

- SLACK_WEBHOOK: Slack token to give notifications on how the scraping process is going and whether any maintenance is required.

---
#### Docker Volumes
/app/config:[HOST DIR] -- The files needed within this config folder are "token.json" if you happen to use the Google Calendar scraper. Please follow instructions on the wiki page to create this "token.json" file.

---
## Library: publishing to several sites

`start_event_engine` can publish to more than one destination, picking one per
event. For example, two Mobilizon instances: a family-friendly site and a
nightlife site.

1. Tag each source in its group package JSON. Any key of a `groupKernels` entry
   that the engine doesn't use itself is kept on the kernel as
   `kernel.source_info`:

```json
"groupKernels": {
  "Sea Tea Improv": {
    "family_friendly": false,
    "calendarType": "ICAL",
    "calendarIDs": ["https://example.com/calendar.ics"],
    "...": "..."
  }
}
```

2. Create one publisher per site, and a function that returns the name of the
   publisher each event goes to (or `None` to skip it):

```python
from calendar_event_engine.Runner import start_event_engine
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader

with SQLiteDB() as cache_db:
    publishers = {
        "ctgrassroots": MobilizonUploader(
            False,
            cache_db,
            endpoint="https://ctgrassroots.org/api",
            email="...",
            password="...",
        ),
        "underground": MobilizonUploader(
            False,
            cache_db,
            endpoint="https://underground.example/api",
            email="...",
            password="...",
        ),
    }
    route_event = lambda event, kernel: (
        "ctgrassroots" if kernel.source_info.get("family_friendly") else "underground"
    )
    start_event_engine(
        "https://example.com/submission.json",
        cache_db,
        publishers=publishers,
        route_event=route_event,
        custom_scrapers=[...],  # optional: a plain list of CustomScraperJob
    )
```

How it behaves:
- `publishers` replaces the publisher built from the submission JSON's key; the
  submission still lists the group packages to scrape.
- `MobilizonUploader` uses `endpoint`, `email` and `password` when given, and
  falls back to `MOBILIZON_ENDPOINT`, `MOBILIZON_EMAIL`/`MOBILIZON_PASSWORD` or
  `MOBILIZON_LOGIN_FILE` for any that are `None`.
- Events routed to `None`, or to a name that isn't in `publishers`, are logged
  and skipped. Skipped events aren't cached, so they are tried again next run.
- Every publisher is connected and closed once per scrape cycle. If one can't
  connect, its events are skipped for that cycle and the others still publish.
- With a single publisher, `route_event` is optional. With several, it is
  required (the engine raises `ValueError` at startup otherwise).
- Without `publishers` or `route_event`, everything works as before.
- Each cached event records the site it was published to: the publisher's name
  in `publishers` (e.g. `"ctgrassroots"`), otherwise `MobilizonUploader`'s
  `site_name` argument, or by default its endpoint's host name.

## Updating Changed Events

Every scrape compares each upcoming event with the version that was published:
new events are created, events that changed (title, time, description, location,
picture, ...) are updated in place on the site they were published to, and
unchanged events are skipped.

An event is recognised by the ID its source gives it (iCal `UID`, Google Calendar
event ID, RSS `guid`, JSON-LD `@id` or `url`), so a renamed or rescheduled event is
updated rather than published again. Events without such an ID (static and most
custom scrapers, unless they set `GenericEvent.source_event_id`) are recognised by
their title and start time, so only their other details can be updated.

A cache created by an older version is upgraded when it is opened. Its events are
not republished: the first scrape records their current version, and later
changes are updated.
