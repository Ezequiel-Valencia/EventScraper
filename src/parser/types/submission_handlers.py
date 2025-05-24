from src.db_cache import SQLiteDB
from src.parser.types.submission import GroupPackage, ScraperTypes
from src.publishers.abc_publisher import Publisher
from src.scrapers.abc_scraper import Scraper



class RunnerSubmission:
    def __init__(self, submitted_db: SQLiteDB,
                 submitted_publishers: {Publisher: [GroupPackage]},
                 test: bool,
                 respective_scrapers: {ScraperTypes: Scraper}):
        self.cache_db = submitted_db
        self.test = test
        self.publishers = submitted_publishers
        self.respective_scrapers = respective_scrapers



