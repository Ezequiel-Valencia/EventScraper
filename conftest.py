import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--mock-only",
        action="store_true",
        default=False,
        help="Run only mocked/unit tests, skipping integration tests that hit live services.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--mock-only"):
        return
    skip = pytest.mark.skip(reason="Skipped: --mock-only flag set")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)
