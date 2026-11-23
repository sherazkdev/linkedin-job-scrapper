"""Trusted client IP resolution for alert rate limits (no blind X-Forwarded-For)."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from app.core.config import Settings


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def client_ip_for_rate_limit(request: Request, settings: Settings) -> str:
    """
    Use direct peer IP unless explicitly configured to trust a single proxy header.

    We never parse multi-hop X-Forwarded-For chains (spoofable from clients).
    """
    if settings.alerts_rate_limit_trust_x_real_ip:
        real_ip = (request.headers.get("X-Real-IP") or "").strip()
        if real_ip and _valid_ip(real_ip):
            return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"