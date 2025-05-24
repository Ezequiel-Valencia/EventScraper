import unittest

from src.scrapers.Websites.cafe9 import Cafe9Scraper


class TestCafe9(unittest.TestCase):


    def test_retrieve_from_source(self):
        """
        Simple test because there are no event's that stay forever where the content can be statically checked
        against known information. Events which stay after 2 days are deleted.
        """
        events_from_cafe9 = Cafe9Scraper(None).retrieve_from_source(None)[0]
        for event in events_from_cafe9.events:
            self.assertTrue((".jpg" in event.picture) or (".png" in event.picture))
            self.assertTrue(len(event.description) != 0)
            self.assertTrue(len(event.begins_on) != 0)
            self.assertTrue(len(event.title) != 0)

if __name__ == '__main__':
    unittest.main()
