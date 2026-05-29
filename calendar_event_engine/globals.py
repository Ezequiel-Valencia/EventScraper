
from slack_sdk.webhook import WebhookClient


_slack_web_hook: WebhookClient | None = None


def set_slack_webhook(web_hook: WebhookClient | None) -> None:
    _slack_web_hook = web_hook


def get_slack_webhook() -> WebhookClient | None:
    return _slack_web_hook


