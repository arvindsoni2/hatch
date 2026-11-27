"""Guarded HTTP(S) fetching for user- and advert-supplied URLs.

The public API is ``validate_public_url`` and ``fetch``. All URL resolution
happens once per hop, every resolved address is checked, and the connection is
made to the validated address while TLS keeps the original hostname.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore
import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
FIXED_HOST_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
MAX_REDIRECTS = 5
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 15.0
TOTAL_TIMEOUT_SECONDS = 30.0

Resolver = Callable[[str, int], Sequence[str]]

_NAT64_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")

_ERROR_MESSAGES = {
    "bad_scheme": "Only http/https public job URLs are allowed",
    "bad_url": "URL has no hostname",
    "userinfo_not_allowed": "URLs with credentials are not allowed",
    "blocked_address": "SSRF blocked: URL resolves to a private, reserved, link-local, or loopback address",
    "resolve_error": "URL hostname could not be resolved",
    "connect_error": "URL connection failed",
    "too_many_redirects": "Job URL exceeded the redirect limit",
    "redirect_loop": "Job URL exceeded the redirect limit",
    "bad_redirect": "Redirect did not include a location",
    "too_large": "Job page exceeds the 2 MB limit",
    "bad_content_type": "Job URL did not return HTML or text",
    "timeout": "URL request timed out",
    "http_error": "URL request failed",
}


class PublicFetchError(ValueError):
    """A safe, code-bearing failure from the guarded fetch service."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        if message is None:
            message = _ERROR_MESSAGES.get(code, "URL request failed")
            if code == "http_error" and status_code is not None:
                message = f"URL returned HTTP {status_code}"
        super().__init__(message)


@dataclass(frozen=True)
class FetchResponse:
    """The bounded result of one guarded fetch."""

    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.content)


def _resolve_host(host: str, port: int) -> Sequence[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        if address not in addresses:
            addresses.append(address)
    return addresses


def _unwrap_addresses(address: ipaddress.IPv4Address | ipaddress.IPv6Address):
    yield address
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            yield address.ipv4_mapped
        if address.sixtofour is not None:
            yield address.sixtofour
        if address in _NAT64_NETWORK:
            yield ipaddress.IPv4Address(address.packed[-4:])


def _validate_addresses(addresses: Sequence[str]) -> tuple[str, ...]:
    if not addresses:
        raise PublicFetchError("resolve_error")
    validated: list[str] = []
    for raw in addresses:
        try:
            address = ipaddress.ip_address(str(raw).split("%", 1)[0])
        except ValueError as exc:
            raise PublicFetchError("blocked_address") from exc
        if not all(candidate.is_global for candidate in _unwrap_addresses(address)):
            raise PublicFetchError("blocked_address")
        rendered = str(address)
        if rendered not in validated:
            validated.append(rendered)
    return tuple(validated)


def validate_public_url(url: str, *, resolver: Resolver | None = None) -> tuple[str, ...]:
    """Validate a URL and return every validated address.

    Every resolved address must be global. IPv4-mapped IPv6, 6to4 and NAT64
    addresses are unwrapped and their embedded IPv4 address is checked too.
    """
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        hostname = parts.hostname
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise PublicFetchError("bad_url") from exc

    if scheme not in {"http", "https"}:
        raise PublicFetchError("bad_scheme")
    if parts.username is not None or parts.password is not None:
        raise PublicFetchError("userinfo_not_allowed")
    if not hostname:
        raise PublicFetchError("bad_url")
    if port < 1 or port > 65535:
        raise PublicFetchError("bad_url")

    try:
        addresses = (resolver or _resolve_host)(hostname, port)
    except OSError as exc:
        raise PublicFetchError("resolve_error") from exc
    return _validate_addresses(addresses)


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve once, validate every address, and connect to a validated IP."""

    def __init__(
        self,
        *,
        inner: httpcore.AsyncNetworkBackend | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._inner = inner or httpcore.AnyIOBackend()
        self._resolver = resolver or _resolve_host
        self._pinned: dict[str, tuple[str, ...]] = {}

    @staticmethod
    def _key(host: str) -> str:
        return host.rstrip(".").lower()

    def pin(self, host: str, addresses: Sequence[str]) -> None:
        self._pinned[self._key(host)] = _validate_addresses(addresses)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        key = self._key(host)
        addresses = self._pinned.get(key)
        if addresses is None:
            resolved = await asyncio.to_thread(self._resolver, host, port)
            addresses = _validate_addresses(resolved)
            self._pinned[key] = addresses
        return await self._inner.connect_tcp(
            addresses[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        raise PublicFetchError("blocked_address")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _transport_for(backend: httpcore.AsyncNetworkBackend) -> httpx.AsyncHTTPTransport:
    pool = httpcore.AsyncConnectionPool(
        network_backend=backend,
        max_connections=10,
        max_keepalive_connections=0,
        keepalive_expiry=0.0,
        http1=True,
        http2=False,
        retries=0,
    )
    transport = httpx.AsyncHTTPTransport(
        trust_env=False,
        http1=True,
        http2=False,
        retries=0,
    )
    # The transport's default pool is replaced so every connection uses the
    # guarded backend. It has not opened any connection at this point.
    transport._pool = pool  # type: ignore[attr-defined]
    return transport


def _loop_key(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            parts.query,
            "",
        )
    )


def _content_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


async def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise PublicFetchError("too_large")
        chunks.append(chunk)
    return b"".join(chunks)


async def fetch(
    url: str,
    *,
    allowed_content_types: Sequence[str] = DEFAULT_ALLOWED_CONTENT_TYPES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    headers: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver | None = None,
    inner_backend: httpcore.AsyncNetworkBackend | None = None,
    total_timeout: float = TOTAL_TIMEOUT_SECONDS,
) -> FetchResponse:
    """Fetch one URL, revalidating every redirect hop and bounding the body."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    allowed = tuple(content_type.lower() for content_type in allowed_content_types)
    current = url
    redirects = 0
    seen = {_loop_key(url)}
    timeout = httpx.Timeout(
        READ_TIMEOUT_SECONDS,
        connect=CONNECT_TIMEOUT_SECONDS,
        write=READ_TIMEOUT_SECONDS,
        pool=CONNECT_TIMEOUT_SECONDS,
    )

    try:
        async with asyncio.timeout(total_timeout):
            while True:
                addresses = await asyncio.to_thread(
                    validate_public_url, current, resolver=resolver
                )
                hop_transport = transport
                if hop_transport is None:
                    backend = GuardedNetworkBackend(
                        inner=inner_backend,
                        resolver=resolver,
                    )
                    backend.pin(urlsplit(current).hostname or "", addresses)
                    hop_transport = _transport_for(backend)

                try:
                    async with httpx.AsyncClient(
                        transport=hop_transport,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=timeout,
                    ) as client:
                        async with client.stream("GET", current, headers=headers) as response:
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location:
                                    raise PublicFetchError("bad_redirect")
                                redirects += 1
                                if redirects > MAX_REDIRECTS:
                                    raise PublicFetchError("too_many_redirects")
                                next_url = urljoin(current, location)
                                next_key = _loop_key(next_url)
                                if next_key in seen:
                                    raise PublicFetchError("redirect_loop")
                                seen.add(next_key)
                                current = next_url
                                continue

                            if 300 <= response.status_code < 400:
                                raise PublicFetchError(
                                    "bad_redirect",
                                    status_code=response.status_code,
                                )
                            if response.status_code >= 400:
                                raise PublicFetchError(
                                    "http_error",
                                    status_code=response.status_code,
                                )
                            if _content_type(response.headers) not in allowed:
                                raise PublicFetchError("bad_content_type")
                            content = await _read_limited(response, max_bytes)
                            return FetchResponse(
                                url=str(response.url),
                                status_code=response.status_code,
                                headers=response.headers,
                                content=content,
                            )
                except PublicFetchError:
                    raise
                except httpx.TimeoutException as exc:
                    raise PublicFetchError("timeout") from exc
                except httpx.ConnectError as exc:
                    raise PublicFetchError("connect_error") from exc
                except httpx.HTTPError as exc:
                    raise PublicFetchError("http_error") from exc
    except TimeoutError as exc:
        raise PublicFetchError("timeout") from exc
