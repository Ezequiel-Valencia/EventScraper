
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.submission import ScraperTypes, GroupPackage


class RunnerSubmission:
    respective_scrapers: dict[ScraperTypes, Scraper]
    publishers: dict[Publisher, list[GroupPackage]]
    def __init__(self, submitted_db: SQLiteDB,
                 submitted_publishers: dict[Publisher, list[GroupPackage]],
                 test: bool,
                 respective_scrapers: dict[ScraperTypes, Scraper]):
        self.cache_db = submitted_db
        self.test = test
        self.publishers = submitted_publishers
        self.respective_scrapers = respective_scrapers



