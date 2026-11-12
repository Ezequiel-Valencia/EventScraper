import json

import httpx2

from calendar_event_engine.types.generics import GenericAddress, GenericEvent
from calendar_event_engine.types.submission import (
    ScraperTypes,
    GroupPackage,
    TimeInfo,
    GroupEventsKernel,
)


_SCRAPER_TYPES_BY_NAME: dict[str, ScraperTypes] = {
    "STATIC": ScraperTypes.STATIC,
    "GOOGLE_CAL": ScraperTypes.GOOGLE_CAL,
    "ICAL": ScraperTypes.ICAL,
    "RSS": ScraperTypes.RSS,
    "JSON_LD": ScraperTypes.JSON_LD,
    "CUSTOM": ScraperTypes.CUSTOM,
}


def retrieve_source_type(source_type_string: str) -> ScraperTypes:
    try:
        return _SCRAPER_TYPES_BY_NAME[source_type_string]
    except KeyError:
        raise TypeError(
            "Expected a string that resolves to a scraper type, instead got: "
            + str(source_type_string)
        ) from None


def get_group_package(json_path: str) -> GroupPackage:
    try:
        response = httpx2.get(json_path, timeout=30, follow_redirects=True)
        response.raise_for_status()
        group_schema: dict = response.json()
    except (httpx2.HTTPError, httpx2.InvalidURL) as e:
        raise RuntimeError(
            f"Failed to fetch group package from {json_path}: {e}"
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON received from {json_path}: {e}") from e

    group_package = GroupPackage(
        {}, group_schema.get("name"), group_schema.get("description")
    )

    for group_name, group_info in group_schema["groupKernels"].items():
        event_address = (
            None
            if "defaultLocation" not in group_info
            else GenericAddress(**group_info["defaultLocation"])
        )
        event_kernel = GenericEvent(
            group_info["publisherInfo"],
            group_info.get("title"),
            group_info.get("beginsOn"),
            group_info.get("defaultDescription"),
            group_info.get("endsOn"),
            group_info["onlineAddress"],
            group_info.get("phoneAddress"),
            event_address,
        )

        calendar_ids = group_info["calendarIDs"]
        scraper_type: ScraperTypes = retrieve_source_type(group_info["calendarType"])
        time_info = None
        if scraper_type == ScraperTypes.STATIC:
            time_info = TimeInfo(group_info["defaultTimes"], group_info["endDate"])

        group_package.scraper_type_and_kernels.setdefault(scraper_type, []).append(
            GroupEventsKernel(
                event_kernel,
                group_name,
                calendar_ids=calendar_ids,
                scraper_type=scraper_type,
                json_source_url=json_path,
                default_time_info=time_info,
            )
        )

    return group_package
