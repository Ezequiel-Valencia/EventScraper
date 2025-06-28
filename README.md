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
