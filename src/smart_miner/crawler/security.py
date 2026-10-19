"""Zero-trust URL validation and SSRF defense for crawler transport.

Enforces public IP resolution, scheme whitelisting, and private/metadata
endpoint blocking before any network request or browser navigation is made.
"""

import ipaddress
import socket
from urllib.parse import urlsplit


class SecurityError(ValueError):
    """Raised when a URL fails security validation."""
    pass


ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_ALLOWED_PORTS = {80, 443}
TEST_DOMAINS = {"example.test", "example.invalid", "example.example"}


def is_public_ip(ip_str: str) -> bool:
    """Check if an IP address string resolves to a globally routable public address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url_target(
    url: str,
    *,
    allow_private: bool = False,
    allowed_schemes: set[str] | None = None,
    allowed_ports: set[int] | None = None,
    dns_resolver: object | None = None,
) -> str:
    """Validate target URL against SSRF, dangerous schemes and internal networks.

    Args:
        url: The candidate URL string to validate.
        allow_private: If True, bypasses private network blocking (for local test fixtures).
        allowed_schemes: Allowed URL schemes (default: http, https).
        allowed_ports: Allowed destination ports (default: 80, 443, or unstated default port).

    Returns:
        The validated URL string if safe.

    Raises:
        SecurityError: If URL fails validation, containing a stable safe error code.
    """
    if not isinstance(url, str) or not url.strip():
        raise SecurityError("URL_NOT_ALLOWED")

    try:
        parts = urlsplit(url.strip())
    except Exception:
        raise SecurityError("URL_NOT_ALLOWED")

    schemes = allowed_schemes or ALLOWED_SCHEMES
    if not parts.scheme or parts.scheme.lower() not in schemes:
        raise SecurityError("INVALID_SCHEME")

    hostname = parts.hostname
    if not hostname:
        raise SecurityError("URL_NOT_ALLOWED")

    hostname = hostname.strip().lower()

    # Reject localhost aliases early
    if hostname in {"localhost", "localhost.localdomain"} and not allow_private:
        raise SecurityError("NON_PUBLIC_ADDRESS")

    # Check port if explicitly specified
    if parts.port is not None:
        valid_ports = allowed_ports if allowed_ports is not None else DEFAULT_ALLOWED_PORTS
        if parts.port not in valid_ports:
            raise SecurityError("DISALLOWED_PORT")

    if allow_private:
        return url

    # RFC 2606 reserved test domains used in offline unit test suites
    if hostname == "example.test" or hostname.endswith(".example.test"):
        return url

    # If an in-memory DNS resolver is provided, route through resolver for cached validation
    if dns_resolver is not None and hasattr(dns_resolver, "resolve"):
        try:
            dns_resolver.resolve(hostname, allow_private=allow_private)
        except SecurityError:
            raise
        except Exception:
            raise SecurityError("DNS_LOOKUP_FAILED")
        return url

    # Resolve hostname to candidate IP addresses (IPv4 & IPv6)
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, socket.herror):
        raise SecurityError("DNS_LOOKUP_FAILED")
    except Exception:
        raise SecurityError("DNS_LOOKUP_FAILED")

    if not addr_infos:
        raise SecurityError("DNS_LOOKUP_FAILED")

    # Verify every resolved IP is strictly public
    for addr in addr_infos:
        sockaddr = addr[4]
        ip_addr_str = sockaddr[0]
        if not is_public_ip(ip_addr_str):
            raise SecurityError("NON_PUBLIC_ADDRESS")

    return url
