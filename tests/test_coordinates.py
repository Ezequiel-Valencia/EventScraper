from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader
from calendar_event_engine.publishers.mobilizon.types import to_mobilizon_geom
from calendar_event_engine.types.generics import GenericAddress, GenericEvent


def test_to_mobilizon_geom_is_longitude_first():
    assert to_mobilizon_geom(41.7677107, -72.6796498) == "-72.6796498;41.7677107"
    assert to_mobilizon_geom(None, -72.6796498) is None
    assert to_mobilizon_geom(41.7677107, None) is None


def test_mobilizon_converter_formats_geom():
    event = GenericEvent(
        publisher_specific_info={"mobilizon": {"groupID": 1}},
        title="Title",
        begins_on="2026-11-11T10:00:00-05:00",
        physical_address=GenericAddress(
            locality="Hartford", latitude=41.7677107, longitude=-72.6796498
        ),
    )
    mobilizon_event = MobilizonUploader.generic_event_converter(event)
    assert mobilizon_event.physicalAddress is not None
    assert mobilizon_event.physicalAddress.geom == "-72.6796498;41.7677107"
