"""Slack alerts about how scraping is going and whether maintenance is needed."""

from enum import Enum

from slack_sdk.webhook import WebhookClient

from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)


class Priority(Enum):
    """Alert priority, with the colour of its Slack attachment."""

    MEDIUM = "#e6e209"
    HIGH = "#ab1a13"


_slack_web_hook: WebhookClient | None = None


def set_slack_webhook(web_hook: WebhookClient | None) -> None:
    global _slack_web_hook
    _slack_web_hook = web_hook


def get_slack_webhook() -> WebhookClient | None:
    return _slack_web_hook


def _slack_attachment(title: str, text: str, priority: Priority) -> dict:
    return {
        "color": priority.value,
        "author_name": "CTEvent Scraper",
        "author_icon": "https://ctgrassroots.org/favicon.ico",
        "title": title,
        "text": text,
        "fields": [
            {"title": "Priority", "value": priority.name.title(), "short": False}
        ],
        "footer": "CTEvent Scraper",
    }


def send_slack_alert(title: str, text: str, priority: Priority) -> None:
    """Post an alert if a webhook is configured. Never raises: failing to
    notify must not stop scraping."""
    web_hook = _slack_web_hook
    if web_hook is None:
        return
    try:
        web_hook.send(attachments=[_slack_attachment(title, text, priority)])
    except Exception as err:
        logger.warning(f"Unable to send Slack alert '{title}'", exc_info=err)
