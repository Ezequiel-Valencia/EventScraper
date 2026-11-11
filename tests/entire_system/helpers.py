"""Shared constants, types and queries for the entire-system tests."""

import uuid
from dataclasses import dataclass

from gql import gql

from testcontainers.core.container import DockerContainer

from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI

MOBILIZON_IMAGE = "kaihuri/mobilizon:5.2.0"
POSTGIS_IMAGE = "postgis/postgis:16-3.4-alpine"
MOBILIZON_PORT = 4000

DB_NAME = DB_USER = DB_PASSWORD = "mobilizon"

BOT_USERNAME = "eventbot"

EVENT_QUERY = gql(
    """
query Event($uuid: UUID!) {
  event(uuid: $uuid) {
    id
    uuid
    title
    description
    beginsOn
    endsOn
    category
    onlineAddress
    tags { title }
    picture { url }
    attributedTo { id }
    organizerActor { id }
    physicalAddress { locality street postalCode region country }
  }
}
"""
)

CREATE_GROUP = gql(
    """
mutation CreateGroup($preferredUsername: String!, $name: String) {
  createGroup(preferredUsername: $preferredUsername, name: $name) { id preferredUsername }
}
"""
)

GROUP_EVENTS_QUERY = gql(
    """
query GroupEvents($preferredUsername: String!) {
  group(preferredUsername: $preferredUsername) {
    organizedEvents(limit: 100) { total elements { uuid title } }
  }
}
"""
)


@dataclass(frozen=True)
class MobilizonUser:
    email: str
    password: str
    username: str


@dataclass(frozen=True)
class MobilizonServer:
    endpoint: str
    container: DockerContainer

    def create_user(self, username: str | None = None) -> MobilizonUser:
        """Create an admin user with a profile through mobilizon_ctl.

        Tests that log in on their own use a fresh user so the groups and
        events they create are isolated from other tests.
        """
        username = username or f"bot{uuid.uuid4().hex[:10]}"
        user = MobilizonUser(f"{username}@example.com", "EventBotPassword123", username)
        # mobilizon_ctl splits arguments on whitespace, so no value may
        # contain spaces.
        exit_code, output = self.container.exec(
            [
                "/bin/mobilizon_ctl",
                "users.new",
                user.email,
                "--password",
                user.password,
                "--admin",
                "--profile-username",
                username,
                "--profile-display-name",
                username,
            ]
        )
        assert exit_code == 0, output.decode()
        return user

    def reset_rate_limits(self) -> None:
        """Forget every request counted by Mobilizon's rate limiter.

        Mobilizon 5.2 limits `login` to 5/min per email and 10/min per IP, and
        the IP counter is shared with createEvent/uploadMedia. Every test call
        comes from the same IP, so without a reset the suite starts failing
        with "Too many requests". The limits are compiled into the release, so
        the Hammer ETS table is cleared over RPC instead.
        """
        exit_code, output = self.container.exec(
            [
                "/bin/mobilizon",
                "rpc",
                ":ets.delete_all_objects(:hammer_ets_buckets)",
            ]
        )
        assert exit_code == 0, output.decode()

    def login(self, user: MobilizonUser) -> MobilizonAPI:
        return MobilizonAPI(self.endpoint, user.email, user.password)


@dataclass(frozen=True)
class MobilizonGroup:
    id: int
    preferred_username: str


def fetch_event(api: MobilizonAPI, event_uuid: str) -> dict:
    return api._execute(EVENT_QUERY, {"uuid": event_uuid})["event"]


def fetch_group_events(api: MobilizonAPI, group: MobilizonGroup) -> list[dict]:
    result = api._execute(
        GROUP_EVENTS_QUERY, {"preferredUsername": group.preferred_username}
    )
    return result["group"]["organizedEvents"]["elements"]


def create_group(api: MobilizonAPI) -> MobilizonGroup:
    """Create a fresh group administered by `api`'s user."""
    username = f"group_{uuid.uuid4().hex[:12]}"
    created = api._execute(
        CREATE_GROUP, {"preferredUsername": username, "name": username}
    )["createGroup"]
    return MobilizonGroup(int(created["id"]), created["preferredUsername"])
