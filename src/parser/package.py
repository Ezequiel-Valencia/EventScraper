import json
import urllib

from src.types.generics import GenericAddress, GenericEvent
from src.types.submission import ScraperTypes, GroupPackage, TimeInfo, GroupEventsKernel


def none_if_not_present(x, dictionary):
    return None if x not in dictionary else dictionary[x]


def retrieve_source_type(source_type_string) -> ScraperTypes:
    match source_type_string:
        case "STATIC":
            return ScraperTypes.STATIC
        case "GOOGLE_CAL":
            return ScraperTypes.GOOGLE_CAL
        case "ICAL":
            return ScraperTypes.ICAL
        case "CUSTOM":
            return ScraperTypes.CUSTOM
    raise TypeError("Expected a string that resolves to a scraper type, instead got: " + source_type_string)


def get_group_package(json_path: str) -> GroupPackage:
    group_schema: dict = None
    with urllib.request.urlopen(json_path) as f:
        group_schema = json.load(f)

    group_package: GroupPackage = GroupPackage({}, none_if_not_present("name", group_schema),
                                               none_if_not_present("description", group_schema))

    for group_name, group_info in group_schema["groupKernels"].items():

        event_address = None if "defaultLocation" not in group_info else GenericAddress(**group_info["defaultLocation"])
        event_kernel = GenericEvent(group_info["publisherInfo"], none_if_not_present("title", group_info),
                                    none_if_not_present("beginsOn", group_info),
                                    none_if_not_present("defaultDescription", group_info),
                                    none_if_not_present("endsOn", group_info),
                                    group_info["onlineAddress"], none_if_not_present("phoneAddress", group_info),
                                    event_address)

        calendar_ids = group_info["calendarIDs"]
        scraper_type: ScraperTypes = retrieve_source_type(group_info["calendarType"])
        time_info = None
        if scraper_type == ScraperTypes.STATIC:
            time_info = TimeInfo(group_info["defaultTimes"], group_info["endDate"])



        if scraper_type not in group_package.scraper_type_and_kernels:
            group_package.scraper_type_and_kernels[scraper_type] = []

        group_package.scraper_type_and_kernels[scraper_type].append(
            GroupEventsKernel(event_kernel, group_name, calendar_ids=calendar_ids,
                              scraper_type=scraper_type, json_source_url=json_path, time_info=time_info))

    return group_package
