from dataclasses import dataclass

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.submission import ScraperTypes, GroupPackage


@dataclass
class RunnerSubmission:
    cache_db: SQLiteDB
    publishers: dict[Publisher, list[GroupPackage]]
    test: bool
    respective_scrapers: dict[ScraperTypes, Scraper]
