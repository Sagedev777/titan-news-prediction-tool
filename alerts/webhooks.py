"""Webhook alert sender — POST forecast data to a configured endpoint."""
from __future__ import annotations
import logging
import httpx

logger = logging.getLogger("alerts")


def send_webhook(url: str, payload: dict, secret: str = "") -> bool:
    """POST forecast data to a webhook URL."""
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code < 300:
            logger.info(f"Webhook delivered to {url}")
            return True
        logger.warning(f"Webhook {url} returned {resp.status_code}")
        return False
    except Exception as exc:
        logger.error(f"Webhook failed: {exc}", exc_info=True)
        return False
