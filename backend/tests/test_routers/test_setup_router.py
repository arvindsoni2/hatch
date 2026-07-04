from __future__ import annotations

from pathlib import Path

import pytest

from app.routers import setup


@pytest.mark.asyncio
async def test_cloud_endpoint_rejects_secret_fields() -> None:
    with pytest.raises(setup.HTTPException) as error:
        await setup.select_cloud_provider({"provider": "openai", "api_key": "secret"})

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_hardware_endpoint_gives_host_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    response = await setup.setup_hardware()

    assert response == {
        "detected": False,
        "message": "Hardware not detected yet.",
        "next_command": "hatch probe",
    }
