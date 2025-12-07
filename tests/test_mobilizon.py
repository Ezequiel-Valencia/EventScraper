import unittest

import pytest

from calendar_event_engine.Runner import _runner
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI


class TestMobilizonAPI(unittest.TestCase):

    @pytest.mark.skip("Should be run manually")
    def test_upload_n_delete_pictures(self):
        mobilizon_api: MobilizonAPI = MobilizonAPI(
            "https://ctgrassroots.org/graphiql", "", ""
        )
        upload_uuid = mobilizon_api.upload_file("https://cdn.britannica.com/92/100692-050-5B69B59B/Mallard.jpg")
        del_uuid = mobilizon_api.delete_uploaded_file(upload_uuid)
        assert upload_uuid == del_uuid


    def test_create_event(self):
        pass

if __name__ == "__main__":
    unittest.main()