"""Fixtures available to every test in the repository."""

import functools
import http.server
import threading
from collections.abc import Iterator

import pytest

from calendar_event_engine.db.db_cache import SQLiteDB
from tests.helpers import PNG_BYTES, LocalHTTPServer


@pytest.fixture(scope="session")
def local_http_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[LocalHTTPServer]:
    root = tmp_path_factory.mktemp("served")
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LocalHTTPServer(f"http://127.0.0.1:{server.server_port}", root)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def cache_db() -> Iterator[SQLiteDB]:
    """An in-memory cache DB that is closed when the test finishes."""
    with SQLiteDB(test_mode=True) as db:
        yield db


@pytest.fixture(scope="session")
def picture_url(local_http_server: LocalHTTPServer) -> str:
    return local_http_server.add_file("picture.png", PNG_BYTES)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass
