"""Errors safe to present to a person or an agent."""

import re


class ImagegenError(Exception):
    def __init__(self, category: str, message: str, *, request_id: str | None = None):
        super().__init__(message)
        self.category = category
        self.request_id = request_id


def redact(value: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)Bearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", value)
    value = re.sub(r"https?://[^\s\"'<>]+", "[URL REDACTED]", value)
    return value
