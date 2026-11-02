"""SSRF protection for any server-side outbound request whose URL is user- or model-controlled."""
import ipaddress
import socket
from urllib.parse import urlparse
from app.core.config import get_settings
from app.core.errors import bad_request


def assert_public_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("https", "http") or not p.hostname:
        raise bad_request("Only http(s) URLs are allowed", "invalid_url")
    if p.scheme == "http" and get_settings().is_prod:
        raise bad_request("Only https URLs are allowed", "invalid_url")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        raise bad_request("Host could not be resolved", "invalid_url")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise bad_request("URL resolves to a private or reserved address", "blocked_url")
    return url
