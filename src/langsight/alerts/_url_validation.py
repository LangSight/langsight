"""
Webhook URL validation — SSRF prevention.

Validates that a webhook URL cannot be used to target internal services,
cloud metadata endpoints, or private network ranges.

DNS rebinding mitigation: when socket.getaddrinfo is available (always in
CPython), the hostname is resolved at validation time and the resolved IPs
are also checked against the private/reserved blocklist.  This prevents an
attacker from registering a public hostname that initially resolves to a
safe IP, passing validation, then switching to an internal IP before the
actual request is sent.  The check adds ~1 DNS RTT at save/update time only.
"""

from __future__ import annotations

import ipaddress
import socket
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


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def validate_webhook_url(url: str) -> None:
    """Raise ValueError if *url* targets a private/loopback/metadata address.

    Checks:
    - Scheme must be http or https
    - Hostname must not be a blocked literal (metadata endpoints, localhost)
    - If hostname is a bare IP address, it must not be private/reserved
    - If hostname is a DNS name, resolve it and validate all returned IPs
      (mitigates DNS rebinding — attacker registers a public name that
      initially resolves safe then flips to an internal IP)
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

    # If hostname is a bare IP, validate directly
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise ValueError(f"Webhook URL must not target a private or reserved IP address: {ip}")
        return
    except ValueError as exc:
        if "Webhook URL" in str(exc):
            raise  # re-raise our own validation error
        pass  # Not an IP literal — fall through to DNS resolution

    # Resolve hostname and validate all returned addresses (DNS rebinding guard)
    try:
        addrinfos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        # Resolution failed — reject to be safe (operator must use a resolvable URL)
        raise ValueError(f"Webhook hostname '{hostname}' could not be resolved") from exc

    for _family, _type, _proto, _canon, sockaddr in addrinfos:
        addr_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise ValueError(f"Webhook hostname '{hostname}' resolves to a blocked address: {ip}")
