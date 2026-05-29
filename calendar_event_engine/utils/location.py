from geopy import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderRateLimited

from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.types.generics import GenericAddress

logger = create_logger_from_designated_logger(__name__)


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
    try:
        geo_locator = Nominatim(user_agent="Mobilizon Event Bot", timeout=10)
        geo_code_location = geo_locator.geocode(
            f"{address.street}, {address.locality}, {address.postalCode}"
        )
        if geo_code_location is None:
            return default_location, default_location_notif
        address.geom = f"{geo_code_location.longitude};{geo_code_location.latitude}"
        logger.debug(
            f"{event_title}: Outsourced location was {address.street}, {address.locality}"
        )
        return address, ""
    except (GeocoderTimedOut, GeocoderRateLimited) as err:
        logger.debug(
            f"Unable to get coordinates for {event_title} with address {address}.",
            exc_info=err,
        )
        return default_location, default_location_notif
