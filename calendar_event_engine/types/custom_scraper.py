from dataclasses import dataclass

from calendar_event_engine.scrapers.abc_scraper import Scraper


@dataclass
class CustomScraperJob:
    """
    A scraper that implements the 'Scraper' abstract base class, and will
    be executed by the event scraper engine
    """

    scraper_name: str
    description: str
    custom_scraper: Scraper
