import json

import requests
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.requests import RequestsHTTPTransport
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import aiohttp
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.publishers.mobilizon.gql_requests import EventGQL, AuthenticationGQL, ActorsGQL
from calendar_event_engine.publishers.mobilizon.types import MobilizonEvent, Actor

logger = create_logger_from_designated_logger(__name__)


class retry_if_not_exception_type(retry_if_exception):
    """Retries except an exception has been raised of one or more types."""

    def __init__(self, exception_types=Exception):
        self.exception_types = exception_types
        super(retry_if_not_exception_type, self).__init__(
            lambda e: not isinstance(e, exception_types))




class _MobilizonClient:
    class LoginTokens:
        accessToken: str
        refreshToken: str

        def __init__(self, access_token: str, refresh_token: str):
            self.accessToken = access_token
            self.refreshToken = refresh_token

    loginTokens: LoginTokens = None
    client: Client = None
    endpoint: str = None
    headers: dict = None

    def __init__(self, endpoint: str, email: str, password: str):
        self.endpoint = endpoint
        self.client = self._build_client()
        data = self.publish(AuthenticationGQL.loginGQL(email, password))
        login = data['login']
        self.loginTokens = self.LoginTokens(login['accessToken'], login['refreshToken'])
        self.client = self._build_client(self.loginTokens.accessToken)

    def _build_client(self,bearer=None):
        self.headers = dict()
        if bearer is not None:
            self.headers['Authorization'] = 'Bearer ' + bearer

        transport = RequestsHTTPTransport(
            url=self.endpoint,
            headers=self.headers,
            verify=True,
            # retries=3,
        )
        return Client(transport=transport, fetch_schema_from_transport=True)


    def refresh_token(self, refresh_token: str):
        return self.publish(AuthenticationGQL.refreshTokenGQL(refresh_token))

    def log_out(self):
        return self.publish(AuthenticationGQL.logoutGQL(f'"{self.loginTokens.refreshToken}"'))  # void


    # attempts at 0s, 2s, 4s, 8s
    @retry(reraise=True, stop=stop_after_attempt(1),
           wait=wait_exponential(multiplier=2))
    def publish(self, query):
        response = self.client.execute(query)
        return response


class MobilizonAPI:
    _mobilizon_client: _MobilizonClient
    bot_actor: Actor
    
    def __init__(self, endpoint: str, email: str, password: str):
        self._mobilizon_client = _MobilizonClient(endpoint, f'"{email}"', f'"{password}"')
        self.bot_actor = Actor(**self.getActors()["identities"][0])
        logger.info("Logged In Mobilizon")

    
    def bot_created_event(self, event_type: MobilizonEvent) -> dict:
        event_type.organizerActorId = self.bot_actor.id

        event_id = self._mobilizon_client.publish(EventGQL.createEventGQL(event_type))
        return {"id": event_id["createEvent"]["id"], "uuid": event_id["createEvent"]["uuid"]}
    
    def upload_file(self, file_path: str) -> str:
        with requests.get(file_path) as file:
            variables = {"name": "automatically-uploaded-event-bot", "file": "uploaded-file", "actorID": self.bot_actor.id}
            response = requests.post(self._mobilizon_client.endpoint,
                data={
                    "query": EventGQL.uploadMediaRawGQL(),
                    "variables": json.dumps(variables)
                },
                files= {
                    "uploaded-file": file.content
                },
                headers={'Authorization': f'Bearer {self._mobilizon_client.loginTokens.accessToken}',
                         'accept': 'application/json'}
            )
            content = json.loads(response.content)
            if content is None or response.status_code != 200 or "errors" in content:
                return ""
            return content["data"]["uploadMedia"]["id"]

    def logout(self):
        self._mobilizon_client.log_out()
        logger.info("Logged Out")
    
    def getActors(self):
        return self._mobilizon_client.publish(ActorsGQL.getIdentities())
    
    def getGroups(self):
        return self._mobilizon_client.publish(ActorsGQL.getGroups('"eventbot"'))

