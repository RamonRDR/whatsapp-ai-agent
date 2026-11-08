"""Structured, privacy-aware operational events without message text or phone numbers."""

import json
import logging
from typing import Any

logger = logging.getLogger("whatsapp_ai_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def emit(name: str, **fields: Any) -> None:
    safe = {"event": name}
    safe.update(fields)
    logger.info(json.dumps(safe, sort_keys=True, default=str))
