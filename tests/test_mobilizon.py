import unittest

import pytest

from calendar_event_engine.Runner import _runner
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from calendar_event_engine.publishers.mobilizon.types import MobilizonEvent


class TestMobilizonAPI(unittest.TestCase):
    mobilizon_endpoint = "https://ctgrassroots.org/graphiql"

    @pytest.mark.skip("Should be run manually")
    def test_upload_n_delete_pictures(self):
        mobilizon_api: MobilizonAPI = MobilizonAPI(
            self.mobilizon_endpoint, "", ""
        )
        upload_uuid = mobilizon_api.upload_file("https://cdn.britannica.com/92/100692-050-5B69B59B/Mallard.jpg")
        del_uuid = mobilizon_api.delete_uploaded_file(upload_uuid)
        assert upload_uuid == del_uuid


    def test_create_event(self):
        mobilizon_api: MobilizonAPI = MobilizonAPI(
            self.mobilizon_endpoint, "", ""
        )
        event = MobilizonEvent(
            attributedToId=27, title="Test", description="Test", beginsOn="2025-05-25T00:00:00-04:00"
        )
        event_id = mobilizon_api.create_event(event)['id']
        del_id = mobilizon_api.delete_event(event_id)
        assert event_id == del_id



if __name__ == "__main__":
    unittest.main()