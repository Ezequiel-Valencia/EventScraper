"""A synchronous gql transport that sends GraphQL requests with httpx2.

gql's bundled HTTPXTransport imports the original `httpx` package; this
mirrors its behaviour (including which errors it raises) on top of httpx2.
"""

from typing import Any

import httpx2
from gql.transport import Transport
from gql.transport.exceptions import (
    TransportAlreadyConnected,
    TransportClosed,
    TransportProtocolError,
    TransportServerError,
)
from graphql import DocumentNode, ExecutionResult, print_ast


class HTTPX2Transport(Transport):
    def __init__(self, url: str, headers: dict[str, str], timeout: float):
        """
        :param headers: Sent with every request. The dict is read on each
            request, so updating it (e.g. after logging in) takes effect immediately.
        """
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self._client: httpx2.Client | None = None

    def connect(self) -> None:
        if self._client is not None:
            raise TransportAlreadyConnected("Transport is already connected")
        self._client = httpx2.Client(timeout=self.timeout)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def execute(  # type: ignore[override]
        self,
        document: DocumentNode,
        variable_values: dict[str, Any] | None = None,
        operation_name: str | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        if self._client is None:
            raise TransportClosed("Transport is not connected")

        payload: dict[str, Any] = {"query": print_ast(document)}
        if variable_values:
            payload["variables"] = variable_values
        if operation_name:
            payload["operationName"] = operation_name

        response = self._client.post(self.url, json=payload, headers=self.headers)

        try:
            result = response.json()
        except ValueError:
            result = None
        if not isinstance(result, dict) or (
            "data" not in result and "errors" not in result
        ):
            # Not a GraphQL answer: report the HTTP error if there is one.
            try:
                response.raise_for_status()
            except httpx2.HTTPStatusError as e:
                raise TransportServerError(str(e), e.response.status_code) from e
            raise TransportProtocolError(
                f"Server did not return a GraphQL result: {response.text}"
            )

        return ExecutionResult(
            data=result.get("data"),
            errors=result.get("errors"),
            extensions=result.get("extensions"),
        )
