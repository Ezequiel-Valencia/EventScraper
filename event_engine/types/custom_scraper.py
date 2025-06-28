from event_engine.publishers.abc_publisher import Publisher
from event_engine.scrapers.abc_scraper import Scraper


class CustomScraperJob:
    """
    A scraper that implements the 'Scraper' abstract base class, and will
    be executed by the event scraper engine
    """
    scraper_name: str
    description: str
    publication_destination: Publisher
    custom_scraper: Scraper

    def __init__(self, scraper_name: str, description: str,
                 publication_destination: Publisher, custom_scraper: Scraper):
        self.custom_scraper = custom_scraper
        self.publication_destination = publication_destination
        self.description = description
        self.scraper_name = scraper_name