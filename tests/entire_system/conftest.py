"""Fixtures that stand up a real Mobilizon instance with testcontainers.

The stack is a PostGIS database plus the Mobilizon image on a private docker
network. It is started once per test session; tests isolate themselves by
creating their own users and groups.
"""

import secrets
from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer, Reaper
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from tests.entire_system.helpers import (
    BOT_USERNAME,
    DB_NAME,
    DB_PASSWORD,
    DB_USER,
    MOBILIZON_IMAGE,
    MOBILIZON_PORT,
    POSTGIS_IMAGE,
    MobilizonGroup,
    MobilizonServer,
    MobilizonUser,
    create_group,
)


@pytest.fixture(scope="session")
def mobilizon_server() -> Iterator[MobilizonServer]:
    with Network() as network:
        database = (
            DockerContainer(POSTGIS_IMAGE)
            .with_network(network)
            .with_network_aliases("postgres")
            .with_env("POSTGRES_USER", DB_USER)
            .with_env("POSTGRES_PASSWORD", DB_PASSWORD)
            .with_env("POSTGRES_DB", DB_NAME)
            # The image starts a temporary server for initialisation, then
            # restarts; only the second "ready" means TCP connections work.
            .waiting_for(
                LogMessageWaitStrategy(
                    "database system is ready to accept connections", times=2
                ).with_startup_timeout(120)
            )
        )
        mobilizon = (
            DockerContainer(MOBILIZON_IMAGE)
            .with_network(network)
            .with_exposed_ports(MOBILIZON_PORT)
            .with_env("MOBILIZON_DATABASE_HOST", "postgres")
            .with_env("MOBILIZON_DATABASE_USERNAME", DB_USER)
            .with_env("MOBILIZON_DATABASE_PASSWORD", DB_PASSWORD)
            .with_env("MOBILIZON_DATABASE_DBNAME", DB_NAME)
            .with_env("MOBILIZON_INSTANCE_HOST", "localhost")
            .with_env("MOBILIZON_INSTANCE_PORT", str(MOBILIZON_PORT))
            .with_env("MOBILIZON_INSTANCE_FEDERATING", "false")
            .with_env("MOBILIZON_INSTANCE_SECRET_KEY_BASE", secrets.token_hex(32))
            .with_env("MOBILIZON_INSTANCE_SECRET_KEY", secrets.token_hex(32))
            .with_env("MOBILIZON_LOGLEVEL", "info")
            .waiting_for(
                LogMessageWaitStrategy(
                    "Running Mobilizon.Web.Endpoint"
                ).with_startup_timeout(300)
            )
        )
        try:
            with database, mobilizon:
                host = mobilizon.get_container_host_ip()
                port = mobilizon.get_exposed_port(MOBILIZON_PORT)
                yield MobilizonServer(f"http://{host}:{port}/api", mobilizon)
        finally:
            # testcontainers otherwise stops its Ryuk reaper from an atexit
            # hook, after pytest has closed its output streams, which prints a
            # spurious "--- Logging error ---" traceback. Stopping it here,
            # once our own containers are gone, is quiet and equivalent.
            Reaper.delete_instance()


@pytest.fixture(autouse=True)
def _reset_rate_limits(mobilizon_server: MobilizonServer) -> None:
    mobilizon_server.reset_rate_limits()


@pytest.fixture(scope="session")
def mobilizon_api(mobilizon_server: MobilizonServer) -> Iterator[MobilizonAPI]:
    """A bot that stays logged in for the whole session."""
    api = mobilizon_server.login(mobilizon_server.create_user(BOT_USERNAME))
    yield api
    api.logout()


@pytest.fixture
def fresh_user(mobilizon_server: MobilizonServer) -> MobilizonUser:
    """A brand new user, for tests that need to log in themselves."""
    return mobilizon_server.create_user()


@pytest.fixture
def fresh_api(
    mobilizon_server: MobilizonServer, fresh_user: MobilizonUser
) -> Iterator[MobilizonAPI]:
    api = mobilizon_server.login(fresh_user)
    yield api
    api.logout()


@pytest.fixture
def mobilizon_group(mobilizon_api: MobilizonAPI) -> MobilizonGroup:
    return create_group(mobilizon_api)


@pytest.fixture
def mobilizon_env(
    monkeypatch: pytest.MonkeyPatch,
    mobilizon_server: MobilizonServer,
    fresh_user: MobilizonUser,
) -> MobilizonUser:
    """Point MobilizonUploader.connect() at the container, as `fresh_user`."""
    monkeypatch.setenv("MOBILIZON_ENDPOINT", mobilizon_server.endpoint)
    monkeypatch.setenv("MOBILIZON_EMAIL", fresh_user.email)
    monkeypatch.setenv("MOBILIZON_PASSWORD", fresh_user.password)
    return fresh_user
