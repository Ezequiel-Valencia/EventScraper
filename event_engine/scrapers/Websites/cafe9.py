import datetime

import pytz
import requests
from bs4 import BeautifulSoup

from event_engine.logger import create_logger_from_designated_logger
from event_engine.publishers.mobilizon.types import EventParameters
from event_engine.scrapers.abc_scraper import Scraper
from event_engine.types.generics import GenericEvent, GenericAddress
from event_engine.types.submission import GroupEventsKernel, ScraperTypes, EventsToUploadFromCalendarID

logger = create_logger_from_designated_logger(__name__)

class Cafe9Scraper(Scraper):
    def close_connection_to_source(self) -> None:
        pass

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }

    url = "https://cafenine.com"

    group_kernel = GroupEventsKernel(None, "Cafe 9", [url], ScraperTypes.CUSTOM, "")

    def connect_to_source(self):
        pass

    def retrieve_from_source(self, event_kernel) -> list[EventsToUploadFromCalendarID]:
        logger.info("Getting Events From Cafe 9")
        response = requests.get(Cafe9Scraper.url, headers=Cafe9Scraper.headers)
        response.raise_for_status()  # Raise an error for bad status codes

        soup = BeautifulSoup(response.text, 'html.parser')
        events: list[GenericEvent] = []

        for event_section in soup.select('.MuiPaper-root-25, .MuiCard-root-24'):
            divs = event_section.find_all('div', recursive=False)
            a_tag = divs[1].find('a')
            if a_tag and a_tag.has_attr('href'):
                events.append(self.get_pages_content(a_tag['href']))

        return [EventsToUploadFromCalendarID(events, Cafe9Scraper.group_kernel, Cafe9Scraper.url)]

    def get_source_type(self):
        pass

    def get_pages_content(self, href) -> GenericEvent:
        event = GenericEvent.default()
        response = requests.get(Cafe9Scraper.url + href)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        main_div = soup.select_one('#product_details').select_one(".MuiGrid-root")

        sub_main_divs = main_div.select('div')
        img = main_div.find('img')
        if img and img.has_attr('srcset'):
            src_set = img['srcset'].split(',', 1)[0]
            event.picture = src_set.split(' ')[0]

        second_divs_text = sub_main_divs[-3].select('p')
        event.description = ""
        for i in range(len(second_divs_text)):
            if i == 0:
                clean_text = second_divs_text[i].get_text(strip=True).rsplit(" ", 1)[0]
                time = datetime.datetime.strptime(clean_text,
                                                             '%A, %B %d, %Y at %I:%M %p')
                event.begins_on = pytz.timezone("America/New_York").localize(time).isoformat()
            event.description += f'{second_divs_text[i].get_text()}\n'

        event.title = main_div.find('h2').get_text()
        event.online_address = Cafe9Scraper.url + href
        event.physical_address = GenericAddress(
            geom="-72.9238838019238;41.30377450753123", locality="New Haven", postalCode="06510",
        street="250 State St", region="CT")
        event.publisher_specific_info = {"mobilizon":
            {"defaultCategory": EventParameters.Categories.music.value.lower(), "defaultTags": ["bar"], "groupID": 14}
        }
        return event
