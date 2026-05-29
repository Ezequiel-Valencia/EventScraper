import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from calendar_event_engine.parser.package import get_group_package
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.types.submission import ScraperTypes

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name)) as f:
        return f.read()


def _mock_response(status_code: int = 200, text: str = "{}") -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    try:
        mock.json.return_value = json.loads(text)
    except json.JSONDecodeError as e:
        mock.json.side_effect = e
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


class TestGetGroupPackageMocked(unittest.TestCase):
    def test_successful_parse(self):
        fixture = _load_fixture("test_group_package.json")
        with patch("requests.get", return_value=_mock_response(text=fixture)):
            package = get_group_package(
                "https://fixtures.local/test_group_package.json"
            )

        self.assertIn(ScraperTypes.GOOGLE_CAL, package.scraper_type_and_kernels)
        kernels = package.scraper_type_and_kernels[ScraperTypes.GOOGLE_CAL]
        self.assertEqual(1, len(kernels))
        self.assertEqual("Test Group", kernels[0].group_name)
        self.assertEqual(["test-calendar-id"], kernels[0].calendar_ids)
        self.assertEqual(
            1, kernels[0].event_template.publisher_specific_info["mobilizon"]["groupID"]
        )

    def test_network_error_raises_runtime_error(self):
        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_group_package("https://unreachable.local/package.json")
        self.assertIn("Failed to fetch group package", str(ctx.exception))

    def test_http_error_raises_runtime_error(self):
        with patch("requests.get", return_value=_mock_response(status_code=404)):
            with self.assertRaises(RuntimeError) as ctx:
                get_group_package("https://fixtures.local/missing.json")
        self.assertIn("Failed to fetch group package", str(ctx.exception))

    def test_invalid_json_raises_runtime_error(self):
        with patch(
            "requests.get", return_value=_mock_response(text="not valid json{{")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_group_package("https://fixtures.local/bad.json")
        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_timeout_raises_runtime_error(self):
        with patch(
            "requests.get",
            side_effect=requests.exceptions.Timeout("Request timed out"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_group_package("https://fixtures.local/slow.json")
        self.assertIn("Failed to fetch group package", str(ctx.exception))


class TestGetRunnerSubmissionMocked(unittest.TestCase):
    def _make_side_effect(self, group_fixture_text: str):
        submission_fixture = json.dumps(
            {"Mobilizon": ["https://fixtures.local/test_group_package.json"]}
        )

        def side_effect(url, timeout=30):
            if "test_group_package" in url:
                return _mock_response(text=group_fixture_text)
            return _mock_response(text=submission_fixture)

        return side_effect

    def test_successful_parse(self):
        group_fixture = _load_fixture("test_group_package.json")
        with patch("requests.get", side_effect=self._make_side_effect(group_fixture)):
            submission = get_runner_submission(
                "https://fixtures.local/submission.json", True, None
            )

        self.assertEqual(1, len(submission.publishers))

    def test_network_error_raises_runtime_error(self):
        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_runner_submission(
                    "https://unreachable.local/submission.json", True, None
                )
        self.assertIn("Failed to fetch runner submission", str(ctx.exception))

    def test_http_error_raises_runtime_error(self):
        with patch("requests.get", return_value=_mock_response(status_code=500)):
            with self.assertRaises(RuntimeError) as ctx:
                get_runner_submission(
                    "https://fixtures.local/submission.json", True, None
                )
        self.assertIn("Failed to fetch runner submission", str(ctx.exception))

    def test_invalid_json_raises_runtime_error(self):
        with patch(
            "requests.get", return_value=_mock_response(text="not valid json{{")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_runner_submission(
                    "https://fixtures.local/submission.json", True, None
                )
        self.assertIn("Invalid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
