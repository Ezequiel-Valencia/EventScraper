from calendar_event_engine.scrapers.ical.scraper import _parse_retrieved_location


def test_location_tokens_are_stripped():
    address = _parse_retrieved_location(
        "Venue, 123 Main St, Springfield, IL, 62701", None
    )
    assert address is not None
    assert address.street == "123 Main St"
    assert address.locality == "Springfield"
    assert address.region == "IL"
    assert address.postalCode == "62701"
