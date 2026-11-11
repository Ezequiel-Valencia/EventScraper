from functools import lru_cache

from geopy import Nominatim
from geopy.exc import GeocoderServiceError

from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.types.generics import GenericAddress

logger = create_logger_from_designated_logger(__name__)


@lru_cache(maxsize=1024)
def _geocode(query: str) -> tuple[float, float] | None:
    """
    Look up (latitude, longitude) for a query. Results, including "not found", are
    cached so the same venue is only sent to Nominatim once per process, as its
    usage policy asks. Errors propagate and are not cached, so a later call retries.
    """
    geo_locator = Nominatim(user_agent="Mobilizon Event Bot", timeout=10)
    location = geo_locator.geocode(query)
    if location is None:
        return None
    return location.latitude, location.longitude


def find_geolocation_from_address(
    address: GenericAddress | None,
    default_location: GenericAddress | None,
    event_title: str | None,
) -> tuple[GenericAddress | None, str]:
    # Address given is default, so don't need to call Nominatim
    default_location_notif = (
        "with unverified location for address. Please check address on their website"
    )
    if address is None:
        return default_location, default_location_notif
    if default_location == address:
        logger.debug(
            f"{event_title} location included with calendar, but is same as default location."
        )
        return default_location, default_location_notif

    query = ", ".join(
        part.strip()
        for part in (address.street, address.locality, address.postalCode)
        if part and part.strip()
    )
    if not query:
        return default_location, default_location_notif

    try:
        coordinates = _geocode(query)
    except GeocoderServiceError as err:
        # Covers timeouts, rate limiting, and the service being unreachable.
        logger.debug(
            f"Unable to get coordinates for {event_title} with address {address}.",
            exc_info=err,
        )
        return default_location, default_location_notif

    if coordinates is None:
        return default_location, default_location_notif
    address.latitude, address.longitude = coordinates
    logger.debug(
        f"{event_title}: Outsourced location was {address.street}, {address.locality}"
    )
    return address, ""
