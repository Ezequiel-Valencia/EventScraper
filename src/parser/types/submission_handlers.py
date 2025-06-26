from event_scraper_generics.abc_publisher import Publisher
from event_scraper_generics.abc_scraper import Scraper
from event_scraper_generics.types.submission import ScraperTypes, GroupPackage

from src.db_cache import SQLiteDB



class RunnerSubmission:
    respective_scrapers: {ScraperTypes: Scraper}
    publishers: {Publisher: list[GroupPackage]}
    def __init__(self, submitted_db: SQLiteDB,
                 submitted_publishers: {Publisher: list[GroupPackage]},
                 test: bool,
                 respective_scrapers: {ScraperTypes: Scraper}):
        self.cache_db = submitted_db
        self.test = test
        self.publishers = submitted_publishers
        self.respective_scrapers = respective_scrapers



