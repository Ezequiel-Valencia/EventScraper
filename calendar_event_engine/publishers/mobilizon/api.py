import json
import logging

import httpx2
from gql import Client, GraphQLRequest
from gql.transport.exceptions import (
    TransportProtocolError,
    TransportQueryError,
    TransportServerError,
)
from tenacity import (
    retry,
    before_sleep_log,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.publishers.mobilizon import gql_requests as gqlr
from calendar_event_engine.publishers.mobilizon.transport import HTTPX2Transport
from calendar_event_engine.publishers.mobilizon.types import MobilizonEvent, Actor

logger = create_logger_from_designated_logger(__name__)

TIMEOUT_SECONDS = 30

# Only retry failures that may be transient (network errors, 5xx, garbled
# responses). GraphQL errors such as validation or permission problems will
# fail the same way every time, so they are raised immediately.
_retry_transient = retry(
    reraise=True,
    retry=retry_if_exception_type(
        (httpx2.TransportError, TransportServerError, TransportProtocolError)
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2),  # waits 2s, 4s, 8s
)

# Mobilizon's rate limiter (Hammer) counts requests per minute, and the per-IP
# counter is shared by login, createEvent and uploadMedia. When it trips, wait
# out the window and try again instead of dropping the event.
RATE_LIMIT_WAIT_SECONDS = 60
RATE_LIMIT_ATTEMPTS = 5


def _is_rate_limited(error: BaseException) -> bool:
    if isinstance(error, TransportServerError) and error.code == 429:
        return True
    if isinstance(error, httpx2.HTTPStatusError) and error.response.status_code == 429:
        return True
    if isinstance(error, TransportQueryError):
        message = str(error).lower()
        return "too many requests" in message or "too_many_requests" in message
    return False


_retry_rate_limited = retry(
    reraise=True,
    retry=retry_if_exception(_is_rate_limited),
    stop=stop_after_attempt(RATE_LIMIT_ATTEMPTS),
    wait=wait_fixed(RATE_LIMIT_WAIT_SECONDS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


def _is_unauthenticated(error: TransportQueryError) -> bool:
    message = str(error).lower()
    return "unauthenticated" in message or "logged in" in message


class MobilizonAPI:
    def __init__(self, endpoint: str, email: str, password: str):
        self.endpoint = endpoint
        self._credentials = {"email": email, "password": password}
        self._headers: dict[str, str] = {}
        # The transport reads this dict on every request, so updating it after
        # (re)login is enough to authenticate subsequent calls.
        self._client = Client(
            transport=HTTPX2Transport(
                endpoint, headers=self._headers, timeout=TIMEOUT_SECONDS
            ),
            fetch_schema_from_transport=True,
            # Mobilizon's schema does not support deprecation info on input values.
            introspection_args={"input_value_deprecation": False},
        )
        self._login()
        self.bot_actor = Actor(**self.get_actors()["identities"][0])
        logger.info("Logged In Mobilizon")

    def _login(self) -> None:
        self._headers.pop("Authorization", None)
        login = self._execute(gqlr.LOGIN, self._credentials, relogin=False)["login"]
        self._refresh_token: str = login["refreshToken"]
        self._headers["Authorization"] = f"Bearer {login['accessToken']}"

    @_retry_rate_limited
    @_retry_transient
    def _execute_once(self, request: GraphQLRequest, variables: dict | None) -> dict:
        return self._client.execute(GraphQLRequest(request, variable_values=variables))

    def _execute(
        self, request: GraphQLRequest, variables: dict | None = None, relogin=True
    ) -> dict:
        try:
            return self._execute_once(request, variables)
        except TransportQueryError as e:
            # Access tokens are short-lived; log back in once and try again.
            if not relogin or not _is_unauthenticated(e):
                raise
            logger.info("Mobilizon session expired, logging in again")
            self._login()
            return self._execute_once(request, variables)

    def create_event(self, event: MobilizonEvent) -> dict:
        event.organizerActorId = self.bot_actor.id
        variables = event.to_gql_variables()
        created = self._execute(gqlr.create_event(variables), variables)["createEvent"]
        return {"id": created["id"], "uuid": created["uuid"]}

    def delete_event(self, event_id: str) -> str:
        return self._execute(gqlr.DELETE_EVENT, {"eventId": event_id})["deleteEvent"][
            "id"
        ]

    def upload_file(self, file_url: str) -> str | None:
        """Download the file at `file_url` and upload it to Mobilizon.

        :return: The uploaded media's UUID, or None if it could not be uploaded.
        """
        try:
            return self._upload_file(file_url)
        except Exception as e:
            logger.warning(f"Unable to upload picture {file_url}: {e}")
            return None

    @_retry_rate_limited
    @_retry_transient
    def _upload_file(self, file_url: str) -> str:
        with httpx2.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as http:
            file = http.get(file_url)
            file.raise_for_status()
            variables = {
                "name": "automatically-uploaded-event-bot",
                "file": "uploaded-file",
                "actorId": self.bot_actor.id,
            }
            response = http.post(
                self.endpoint,
                data={"query": gqlr.UPLOAD_MEDIA, "variables": json.dumps(variables)},
                files={"uploaded-file": file.content},
                headers={**self._headers, "accept": "application/json"},
            )
            response.raise_for_status()
            content = response.json()
            if content.get("errors"):
                raise TransportQueryError(str(content["errors"]))
            return content["data"]["uploadMedia"]["uuid"]

    def delete_uploaded_file(self, uuid: str) -> str:
        return self._execute(gqlr.REMOVE_MEDIA, {"uuid": uuid})["removeMedia"]["uuid"]

    def logout(self):
        self._execute(gqlr.LOGOUT, {"refreshToken": self._refresh_token})
        logger.info("Logged Out")

    def get_actors(self) -> dict:
        return self._execute(gqlr.IDENTITIES)

    def get_groups(self, name: str = "eventbot", page: int = 1, limit: int = 30):
        return self._execute(gqlr.GROUPS, {"name": name, "page": page, "limit": limit})
