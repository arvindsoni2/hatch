from unittest.mock import patch

from app.schemas.profile import Profile


async def test_summary_returns_insufficient_empty_state(client) -> None:
    with patch("app.services.outcome_learning_service.load_profile", return_value=Profile()):
        response = await client.get("/api/outcome-learning/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["resolved_applications"] == 0
    assert body["confidence"] == "insufficient"
    assert body["additional_required"] == 15


async def test_recompute_empty_job_set(client) -> None:
    with patch("app.services.outcome_learning_service.load_profile", return_value=Profile()):
        response = await client.post("/api/outcome-learning/recompute")
    assert response.status_code == 200
    assert response.json()["jobs_scanned"] == 0


async def test_reset_requires_exact_confirmation(client) -> None:
    response = await client.post("/api/outcome-learning/reset", json={"confirmation": "reset"})
    assert response.status_code == 422


async def test_missing_job_score_returns_404(client) -> None:
    response = await client.get("/api/outcome-learning/jobs/missing")
    assert response.status_code == 404
