"""Contract tests for the guarded public fetch service."""
from __future__ import annotations

import asyncio
import ssl
from collections.abc import Sequence

import httpx
import httpcore
import pytest

from app.services import public_fetch
from app.services.public_fetch import (
    GuardedNetworkBackend,
    PublicFetchError,
    fetch,
    validate_public_url,
)

PUBLIC_IP = "93.184.216.34"
PRIVATE_ADDRESSES = (
    "127.0.0.1",
    "::1",
    "10.0.0.1",
    "192.168.1.10",
    "169.254.169.254",
    "::ffff:127.0.0.1",
    "2002:7f00:1::",
    "64:ff9b::7f00:1",
    "0.0.0.0",
)


def _resolver(mapping: dict[str, Sequence[str]]):
    calls: list[tuple[str, int]] = []

    def resolve(host: str, port: int) -> Sequence[str]:
        calls.append((host, port))
        return mapping[host]

    return resolve, calls


class FakeStream:
    """A tiny HTTP/1.1 stream that records the TLS server name."""

    def __init__(self, body: bytes = b"ok", content_type: str = "text/plain") -> None:
        self.body = body
        self.content_type = content_type
        self.server_hostname: str | None = None
        self._sent = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        head = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {self.content_type}\r\n"
            f"Content-Length: {len(self.body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        return head + self.body

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> "FakeStream":
        self.server_hostname = server_hostname
        return self

    def get_extra_info(self, info: str):
        return None


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, stream: FakeStream | None = None) -> None:
        self.hosts: list[str] = []
        self.stream = stream or FakeStream()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> FakeStream:
        self.hosts.append(host)
        return self.stream

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        raise AssertionError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        return None


class CountingByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: int = 100, size: int = 1024) -> None:
        self.chunks = chunks
        self.size = size
        self.read_chunks = 0

    async def __aiter__(self):
        for _ in range(self.chunks):
            self.read_chunks += 1
            yield b"x" * self.size


class StreamingTransport(httpx.AsyncBaseTransport):
    def __init__(self, stream: CountingByteStream) -> None:
        self.stream = stream

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=self.stream,
        )


def _redirect_transport(location: str) -> tuple[httpx.MockTransport, list[str]]:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": location})

    return httpx.MockTransport(handler), requests


@pytest.mark.parametrize("address", PRIVATE_ADDRESSES)
def test_validate_public_url_blocks_embedded_private_address(address: str) -> None:
    resolver, _ = _resolver({"blocked.test": [address]})

    with pytest.raises(PublicFetchError) as exc:
        validate_public_url("http://blocked.test/path", resolver=resolver)

    assert exc.value.code == "blocked_address"


def test_validate_public_url_blocks_mixed_public_and_private_answers() -> None:
    resolver, _ = _resolver({"mixed.test": [PUBLIC_IP, "10.0.0.1"]})

    with pytest.raises(PublicFetchError) as exc:
        validate_public_url("https://mixed.test/", resolver=resolver)

    assert exc.value.code == "blocked_address"


@pytest.mark.parametrize(
    "url, code",
    [
        ("ftp://example.com/job", "bad_scheme"),
        ("file:///etc/passwd", "bad_scheme"),
        ("http://user:pass@example.com/job", "userinfo_not_allowed"),
        ("http:///no-host", "bad_url"),
    ],
)
def test_validate_public_url_rejects_unsafe_url_shapes(url: str, code: str) -> None:
    resolver, _ = _resolver({"example.com": [PUBLIC_IP]})

    with pytest.raises(PublicFetchError) as exc:
        validate_public_url(url, resolver=resolver)

    assert exc.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("address", PRIVATE_ADDRESSES)
async def test_fetch_blocks_a_redirect_to_a_private_hop(address: str) -> None:
    resolver, _ = _resolver({"public.test": [PUBLIC_IP], "private.test": [address]})
    transport, requests = _redirect_transport("http://private.test/next")

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "http://public.test/start",
            allowed_content_types=("text/html",),
            transport=transport,
            resolver=resolver,
        )

    assert exc.value.code == "blocked_address"
    assert all("private.test" not in request for request in requests)


@pytest.mark.asyncio
async def test_fetch_blocks_a_name_with_mixed_answers_before_requesting() -> None:
    resolver, _ = _resolver({"mixed.test": [PUBLIC_IP, "10.0.0.1"]})
    transport, requests = _redirect_transport("http://mixed.test/next")

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "http://mixed.test/start",
            allowed_content_types=("text/html",),
            transport=transport,
            resolver=resolver,
        )

    assert exc.value.code == "blocked_address"
    assert requests == []


@pytest.mark.asyncio
async def test_backend_resolves_once_and_connects_to_the_first_validated_address() -> None:
    calls: list[str] = []

    def resolver(host: str, port: int) -> Sequence[str]:
        calls.append(host)
        return [PUBLIC_IP] if len(calls) == 1 else ["10.0.0.1"]

    inner = RecordingBackend()
    backend = GuardedNetworkBackend(inner=inner, resolver=resolver)

    await backend.connect_tcp("example.com", 443)

    assert calls == ["example.com"]
    assert inner.hosts == [PUBLIC_IP]


@pytest.mark.asyncio
async def test_pinned_host_does_not_resolve_again() -> None:
    calls: list[str] = []

    def resolver(host: str, port: int) -> Sequence[str]:
        calls.append(host)
        return ["10.0.0.1"]

    inner = RecordingBackend()
    backend = GuardedNetworkBackend(inner=inner, resolver=resolver)
    backend.pin("example.com", [PUBLIC_IP])

    await backend.connect_tcp("example.com", 443)

    assert calls == []
    assert inner.hosts == [PUBLIC_IP]


@pytest.mark.asyncio
async def test_tls_verifies_the_original_hostname_while_connecting_to_the_validated_ip() -> None:
    resolver, _ = _resolver({"example.com": [PUBLIC_IP]})
    inner = RecordingBackend(FakeStream(body=b"ok", content_type="text/plain"))

    response = await fetch(
        "https://example.com/",
        allowed_content_types=("text/plain",),
        resolver=resolver,
        inner_backend=inner,
    )

    assert response.text == "ok"
    assert inner.hosts == [PUBLIC_IP]
    assert inner.stream.server_hostname == "example.com"


@pytest.mark.asyncio
async def test_fetch_stops_streaming_at_the_size_cap() -> None:
    stream = CountingByteStream(chunks=100, size=1024)

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "https://example.com/",
            allowed_content_types=("text/plain",),
            max_bytes=4 * 1024,
            transport=StreamingTransport(stream),
            resolver=_resolver({"example.com": [PUBLIC_IP]})[0],
        )

    assert exc.value.code == "too_large"
    assert stream.read_chunks <= 6


@pytest.mark.asyncio
async def test_fetch_rejects_a_wrong_content_type() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/octet-stream"},
            content=b"data",
        )
    )

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "https://example.com/",
            allowed_content_types=("text/html",),
            transport=transport,
            resolver=_resolver({"example.com": [PUBLIC_IP]})[0],
        )

    assert exc.value.code == "bad_content_type"


@pytest.mark.asyncio
async def test_fetch_rejects_a_redirect_loop() -> None:
    transport, _ = _redirect_transport("https://example.com/loop")

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "https://example.com/loop",
            allowed_content_types=("text/html",),
            transport=transport,
            resolver=_resolver({"example.com": [PUBLIC_IP]})[0],
        )

    assert exc.value.code == "redirect_loop"


@pytest.mark.asyncio
async def test_fetch_rejects_more_than_five_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(302, headers={"location": f"/hop/{number + 1}"})

    transport = httpx.MockTransport(handler)

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "https://example.com/hop/0",
            allowed_content_types=("text/html",),
            transport=transport,
            resolver=_resolver({"example.com": [PUBLIC_IP]})[0],
        )

    assert exc.value.code == "too_many_redirects"


@pytest.mark.asyncio
async def test_fetch_maps_a_total_deadline_to_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, content=b"late")

    transport = httpx.MockTransport(handler)

    with pytest.raises(PublicFetchError) as exc:
        await fetch(
            "https://example.com/",
            allowed_content_types=("text/plain",),
            transport=transport,
            resolver=_resolver({"example.com": [PUBLIC_IP]})[0],
            total_timeout=0.01,
        )

    assert exc.value.code == "timeout"


@pytest.mark.asyncio
async def test_jd_analyser_refuses_a_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jd_analyser as module

    resolver, _ = _resolver({"public.test": [PUBLIC_IP], "private.test": ["10.0.0.1"]})
    transport, requests = _redirect_transport("http://private.test/secret")

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)
    analyser = module.JDAnalyser.__new__(module.JDAnalyser)

    with pytest.raises(PublicFetchError) as exc:
        await analyser._fetch_jd("http://public.test/job")

    assert exc.value.code == "blocked_address"
    assert all("private.test" not in request for request in requests)


@pytest.mark.asyncio
async def test_job_url_importer_refuses_a_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.job_url_importer as module

    resolver, _ = _resolver({"public.test": [PUBLIC_IP], "private.test": ["10.0.0.1"]})
    transport, requests = _redirect_transport("http://private.test/secret")

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)

    with pytest.raises(PublicFetchError) as exc:
        await module.preview_url("http://public.test/job")

    assert exc.value.code == "blocked_address"
    assert all("private.test" not in request for request in requests)


@pytest.mark.asyncio
async def test_company_watchlist_refuses_a_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.company_watchlist as module
    from app.models.company_watchlist import CompanyWatchlistItem

    resolver, _ = _resolver({"public.test": [PUBLIC_IP], "private.test": ["10.0.0.1"]})
    transport, requests = _redirect_transport("http://private.test/secret")

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)
    item = CompanyWatchlistItem(
        company_name="Example",
        careers_url="http://public.test/careers",
        source_type="generic_careers_page",
        scan_frequency="daily",
    )

    with pytest.raises(PublicFetchError) as exc:
        await module.discover_roles_for_item(item)

    assert exc.value.code == "blocked_address"
    assert all("private.test" not in request for request in requests)


@pytest.mark.asyncio
async def test_company_researcher_refuses_a_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.company_researcher as module

    resolver, _ = _resolver({"html.duckduckgo.com": [PUBLIC_IP], "private.test": ["10.0.0.1"]})
    transport, requests = _redirect_transport("http://private.test/secret")

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)
    service = module.CompanyResearchService.__new__(module.CompanyResearchService)

    bundle = await service._scrape_company_info("Example Cloud")

    assert bundle.text == ""
    assert all("private.test" not in request for request in requests)


@pytest.mark.asyncio
async def test_company_researcher_encodes_the_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.company_researcher as module

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><body>no results</body></html>",
        )

    resolver, _ = _resolver({"html.duckduckgo.com": [PUBLIC_IP]})
    transport = httpx.MockTransport(handler)

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)
    service = module.CompanyResearchService.__new__(module.CompanyResearchService)

    await service._scrape_company_info("Example Cloud")

    assert seen
    assert "Example+Cloud" in seen[0]
    assert "Example Cloud" not in seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_name, scraper_name, host",
    [
        ("app.scrapers.indeed_india", "IndeedIndiaScraper", "in.indeed.com"),
        ("app.scrapers.naukri", "NaukriScraper", "www.naukri.com"),
        ("app.scrapers.itjobswatch", "ITJobsWatchScraper", "www.itjobswatch.co.uk"),
        ("app.scrapers.linkedin", "LinkedInScraper", "www.linkedin.com"),
    ],
)
async def test_httpx_scrapers_refuse_a_redirect_to_private(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    scraper_name: str,
    host: str,
) -> None:
    import importlib
    from unittest.mock import AsyncMock

    module = importlib.import_module(module_name)
    resolver, _ = _resolver({host: [PUBLIC_IP], "private.test": ["10.0.0.1"]})
    transport, requests = _redirect_transport("http://private.test/secret")

    async def guarded_fetch(url: str, **kwargs):
        return await public_fetch.fetch(url, transport=transport, resolver=resolver, **kwargs)

    monkeypatch.setattr(module, "fetch", guarded_fetch)
    scraper = getattr(module, scraper_name)()
    scraper.random_delay = AsyncMock()

    assert await scraper.scrape() == []
    assert all("private.test" not in request for request in requests)
