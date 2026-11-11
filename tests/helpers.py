"""Helpers shared by every test in the repository."""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# A valid 1x1 PNG, for tests that need a real image.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@dataclass(frozen=True)
class LocalHTTPServer:
    """Serves files from `root` so tests don't depend on outside websites."""

    base_url: str
    root: Path

    def add_file(self, name: str, content: bytes | str) -> str:
        path = self.root / name
        if isinstance(content, str):
            path.write_text(content)
        else:
            path.write_bytes(content)
        return f"{self.base_url}/{name}"

    def add_json(self, name: str, content: dict) -> str:
        return self.add_file(name, json.dumps(content))


def same_instant(a: str, b: str) -> bool:
    """Whether two ISO 8601 timestamps name the same moment, whatever their offsets."""
    return datetime.fromisoformat(a) == datetime.fromisoformat(b)
