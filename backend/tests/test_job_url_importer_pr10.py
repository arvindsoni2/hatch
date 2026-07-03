import json
from app.services.job_url_importer import extract_job, normalize_url, validate_public_url


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url("HTTPS://Example.COM/job/?utm_source=x&id=2#apply") == "https://example.com/job?id=2"


def test_json_ld_jobposting_extraction():
    payload = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Engineer",
               "hiringOrganization": {"name": "Acme"}, "description": "<p>Build systems</p>"}
    draft = extract_job(f'<script type="application/ld+json">{json.dumps(payload)}</script>', "https://example.com/job")
    assert draft["title"] == "Engineer"
    assert draft["company"] == "Acme"
    assert draft["description"] == "Build systems"


def test_private_url_is_rejected():
    try:
        validate_public_url("http://127.0.0.1/job")
    except ValueError:
        return
    raise AssertionError("private URL accepted")
