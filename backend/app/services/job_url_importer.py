"""SSRF-safe, conservative extraction for user-supplied public job URLs."""
from __future__ import annotations
import html
import ipaddress
import json
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import httpx

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "source"}
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def validate_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.hostname.lower() == "localhost":
        raise ValueError("Only public HTTP(S) job URLs are allowed")
    for info in socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("Private, reserved, link-local, and loopback addresses are not allowed")


def _strip_markup(value: str) -> str:
    value = re.sub(r"<(br|/p|/li)[^>]*>", "\n", value, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def _jobposting(value):
    if isinstance(value, list):
        for item in value:
            found = _jobposting(item)
            if found:
                return found
    if isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            return value
        for item in value.values():
            found = _jobposting(item)
            if found:
                return found
    return None


def extract_job(html_text: str, source_url: str) -> dict:
    posting = None
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, re.I | re.S):
        try:
            posting = _jobposting(json.loads(raw))
        except Exception:
            continue
        if posting:
            break
    if posting:
        org = posting.get("hiringOrganization") or {}
        location = posting.get("jobLocation") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address", {}) if isinstance(location, dict) else {}
        return {"title": posting.get("title"), "company": org.get("name") if isinstance(org, dict) else None,
                "location": ", ".join(str(v) for v in address.values() if v) if isinstance(address, dict) else str(address),
                "description": _strip_markup(posting.get("description", "")),
                "apply_url": posting.get("url") or posting.get("applyUrl") or source_url}
    def first(pattern):
        match = re.search(pattern, html_text, re.I | re.S)
        return _strip_markup(match.group(1)) if match else None
    return {"title": first(r"<h1[^>]*>(.*?)</h1>") or first(r"<title[^>]*>(.*?)</title>"),
            "company": first(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']'),
            "description": first(r"<(?:main|article)[^>]*>(.*?)</(?:main|article)>") or first(r"<body[^>]*>(.*?)</body>"),
            "apply_url": source_url}


async def preview_url(url: str) -> dict:
    current = normalize_url(url)
    headers = {"User-Agent": "Hatch-Job-Importer/1.0"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
        for _ in range(6):
            validate_public_url(current)
            async with client.stream("GET", current, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect did not include a location")
                    current = normalize_url(urljoin(current, location))
                    continue
                content_type = response.headers.get("content-type", "").lower()
                if not any(kind in content_type for kind in ALLOWED_TYPES):
                    raise ValueError("Job URL did not return HTML or text")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise ValueError("Job page exceeds the 2 MB limit")
                    chunks.append(chunk)
                text = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                draft = extract_job(text, current)
                length = len(draft.get("description") or "")
                confidence = "high" if draft.get("title") and draft.get("company") and length >= 800 else "medium" if draft.get("title") and length >= 400 and draft.get("company") else "low"
                method = "direct"
                if confidence == "low":
                    try:
                        from .firecrawl_client import scrape_public_job
                        fallback = await scrape_public_job(current)
                        if fallback:
                            candidate = extract_job(fallback, current)
                            if len(candidate.get("description") or "") > length:
                                draft, length, method = candidate, len(candidate.get("description") or ""), "firecrawl"
                                confidence = "high" if draft.get("title") and draft.get("company") and length >= 800 else "medium" if draft.get("title") and draft.get("company") and length >= 400 else "low"
                    except Exception:
                        pass
                return {**draft, "source_url": url, "normalized_url": normalize_url(url), "final_url": current,
                        "confidence": confidence, "extraction_method": method if confidence != "low" else "manual_required",
                        "warnings": [] if confidence == "high" else ["Review extracted fields before saving."]}
        raise ValueError("Job URL exceeded the redirect limit")
