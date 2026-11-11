import pytest
from gql.transport.exceptions import TransportQueryError

from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from calendar_event_engine.publishers.mobilizon.types import (
    EventParameters,
    MobilizonEvent,
)
from tests.helpers import LocalHTTPServer, same_instant
from tests.entire_system.helpers import (
    BOT_USERNAME,
    MobilizonGroup,
    MobilizonServer,
    MobilizonUser,
    create_group,
    fetch_event,
)

pytestmark = pytest.mark.entire_system


def test_login_resolves_bot_actor(mobilizon_api: MobilizonAPI):
    assert mobilizon_api.bot_actor.preferredUsername == BOT_USERNAME
    assert mobilizon_api.bot_actor.type == "PERSON"


def test_login_with_wrong_password_fails(
    mobilizon_server: MobilizonServer, fresh_user: MobilizonUser
):
    with pytest.raises(TransportQueryError):
        MobilizonAPI(mobilizon_server.endpoint, fresh_user.email, "wrong-pass")


def test_get_groups_lists_bot_memberships(
    mobilizon_api: MobilizonAPI, mobilizon_group: MobilizonGroup
):
    memberships = mobilizon_api.get_groups(name="")["loggedUser"]["memberships"]
    groups = {m["parent"]["id"]: m["role"] for m in memberships["elements"]}
    assert groups[str(mobilizon_group.id)] == "ADMINISTRATOR"


def test_upload_n_delete_pictures(mobilizon_api: MobilizonAPI, picture_url: str):
    upload_uuid = mobilizon_api.upload_file(picture_url)
    assert upload_uuid is not None
    del_uuid = mobilizon_api.delete_uploaded_file(upload_uuid)
    assert upload_uuid == del_uuid


def test_upload_missing_picture_returns_none(
    mobilizon_api: MobilizonAPI, local_http_server: LocalHTTPServer
):
    assert mobilizon_api.upload_file(f"{local_http_server.base_url}/nope.png") is None


def test_create_event(mobilizon_api: MobilizonAPI, mobilizon_group: MobilizonGroup):
    event = MobilizonEvent(
        attributedToId=mobilizon_group.id,
        title="Test",
        description="Test",
        beginsOn="2030-05-25T00:00:00-04:00",
    )
    created = mobilizon_api.create_event(event)

    stored = fetch_event(mobilizon_api, created["uuid"])
    assert stored["id"] == created["id"]
    assert stored["title"] == "Test"
    assert stored["attributedTo"]["id"] == str(mobilizon_group.id)
    assert stored["organizerActor"]["id"] == str(mobilizon_api.bot_actor.id)
    assert same_instant(stored["beginsOn"], "2030-05-25T00:00:00-04:00")

    del_id = mobilizon_api.delete_event(created["id"])
    assert created["id"] == del_id
    with pytest.raises(TransportQueryError, match="event_not_found|Event not found"):
        fetch_event(mobilizon_api, created["uuid"])


def test_create_event_with_every_field(
    mobilizon_api: MobilizonAPI, mobilizon_group: MobilizonGroup, picture_url: str
):
    media_uuid = mobilizon_api.upload_file(picture_url)
    assert media_uuid is not None
    # Quotes, backslashes and braces must survive as data, not break the query.
    title = 'Jazz "Jam" \\ {night}'
    event = MobilizonEvent(
        attributedToId=mobilizon_group.id,
        title=title,
        description="<p>All welcome</p>",
        beginsOn="2030-05-25T19:00:00-04:00",
        endsOn="2030-05-25T22:00:00-04:00",
        tags=["Music", "Jazz"],
        picture=EventParameters.MediaInput(mediaUuid=media_uuid),
        onlineAddress="https://example.com/jazz",
        category=EventParameters.Categories.music,
        physicalAddress=EventParameters.Address(
            locality="Hartford",
            postalCode="06103",
            street="350 Asylum St.",
            geom="-72.6796498;41.7677107",
        ),
    )
    created = mobilizon_api.create_event(event)
    try:
        stored = fetch_event(mobilizon_api, created["uuid"])
        assert stored["title"] == title
        assert "All welcome" in stored["description"]
        assert same_instant(stored["endsOn"], "2030-05-25T22:00:00-04:00")
        assert stored["category"] == "MUSIC"
        assert stored["onlineAddress"] == "https://example.com/jazz"
        assert sorted(t["title"] for t in stored["tags"]) == ["Jazz", "Music"]
        assert stored["picture"] is not None
        address = stored["physicalAddress"]
        assert address["locality"] == "Hartford"
        assert address["street"] == "350 Asylum St."
        assert address["postalCode"] == "06103"
    finally:
        mobilizon_api.delete_event(created["id"])


def test_create_event_in_foreign_group_is_rejected(mobilizon_api: MobilizonAPI):
    event = MobilizonEvent(
        attributedToId=999_999, title="Nope", beginsOn="2030-05-25T00:00:00-04:00"
    )
    with pytest.raises(TransportQueryError):
        mobilizon_api.create_event(event)


def test_relogin_after_session_is_lost(fresh_api: MobilizonAPI):
    group = create_group(fresh_api)
    # Simulate an expired access token: requests go out unauthenticated, so
    # the client has to notice and log in again.
    fresh_api._headers.pop("Authorization")

    created = fresh_api.create_event(
        MobilizonEvent(
            attributedToId=group.id,
            title="After relogin",
            beginsOn="2030-05-25T00:00:00-04:00",
        )
    )
    assert "Authorization" in fresh_api._headers
    assert fresh_api.delete_event(created["id"]) == created["id"]
