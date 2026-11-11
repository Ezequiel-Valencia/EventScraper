import httpx2
import validators

from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.types.generics import GenericEvent

logger = create_logger_from_designated_logger(__name__)

# https://www.geeksforgeeks.org/http-headers-content-type/
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/gif", "image/jpeg", "image/png"})


def is_reachable_image(url: str) -> bool:
    """Whether `url` answers with one of the allowed image content types."""
    try:
        response = httpx2.head(url, timeout=30, follow_redirects=True)
    except (httpx2.HTTPError, httpx2.InvalidURL) as err:
        logger.debug(f"Unable to reach picture {url}: {err}")
        return False
    # The header can carry parameters, e.g. "image/png; charset=binary".
    content_type = response.headers.get("Content-Type", "").split(";")[0]
    return (
        response.is_success
        and content_type.strip().lower() in ALLOWED_IMAGE_CONTENT_TYPES
    )


def normalize_generic_event(
    event: GenericEvent, checked_pictures: dict[str, bool] | None = None
) -> None:
    """
    Blank out a picture or online address the publisher would reject.

    :param checked_pictures: Results of earlier picture checks, keyed by URL.
        Many events share a picture, so passing the same dict for a batch of
        events avoids requesting each picture more than once.
    """
    if checked_pictures is None:
        checked_pictures = {}
    picture = event.picture
    # If valid URL but not a picture, set to empty string
    if picture and validators.url(picture):
        if picture not in checked_pictures:
            checked_pictures[picture] = is_reachable_image(picture)
        if not checked_pictures[picture]:
            event.picture = ""

    if not event.online_address or not validators.url(event.online_address):
        event.online_address = ""
