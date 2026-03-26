"""
Webhook URL validation — SSRF prevention.

Validates that a webhook URL cannot be used to target internal services,
cloud metadata endpoints, or private network ranges.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Well-known metadata and loopback hostnames that must never receive outbound requests
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "169.254.169.254",  # AWS / Azure IMDS
        "metadata.google.internal",  # GCP metadata
        "metadata.internal",
    }
)


def validate_webhook_url(url: str) -> None:
    """Raise ValueError if *url* targets a private/loopback/metadata address.

    Checks:
    - Scheme must be http or https
    - Hostname must not be a blocked literal (metadata endpoints, localhost)
    - If hostname is a bare IP address, it must not be private, loopback,
      link-local, or otherwise reserved

    DNS-based rebinding attacks are out of scope here — that requires
    network-layer controls (egress firewall).
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Invalid webhook URL: {exc}") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Webhook URL scheme must be http or https, got: {parsed.scheme!r}")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Webhook URL has no hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked webhook hostname: {hostname!r}")

    # If hostname is a bare IP, validate it is not a private/reserved range
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return  # Not an IP — hostname string, DNS resolution happens at request time

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        raise ValueError(f"Webhook URL must not target a private or reserved IP address: {ip}")
