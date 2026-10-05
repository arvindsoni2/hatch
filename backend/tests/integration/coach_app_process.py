"""Bounded, test-only runner for the real backend against synthetic local data."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from types import TracebackType

import httpx


BACKEND_DIR = Path(__file__).resolve().parents[2]


class CoachAppProcess:
    def __init__(self, database_path: Path, media_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.media_root = media_root.resolve()
        self._process: asyncio.subprocess.Process | None = None
        self._base_url: str | None = None

    @property
    def pid(self) -> int:
        if self._process is None or self._process.returncode is not None:
            raise RuntimeError("Coach app process is not running")
        return self._process.pid

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            raise RuntimeError("Coach app process is not running")
        return self._base_url

    def _environment(self) -> dict[str, str]:
        root = self.database_path.parent
        config = root / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "ai_runtime.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ai_mode": "not_configured",
                    "feature_gates": {"coach_interview_prep": True},
                }
            ),
            encoding="utf-8",
        )
        return {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL", "TZ", "HOME"}
        } | {
            "PYTHONPATH": str(BACKEND_DIR),
            "DATABASE_URL": f"sqlite+aiosqlite:///{self.database_path}",
            "HATCH_CONFIG_DIR": str(config),
            "HATCH_COACH_MEDIA_ROOT": str(self.media_root),
            "HATCH_COACH_CONVERSATIONAL_ENABLED": "true",
            "HATCH_APP_LOCK_ENABLED": "false",
            "LANGGRAPH_CHECKPOINT_DB": f"sqlite:///{root / 'checkpoints.db'}",
            "DIGEST_ENABLED": "false",
        }

    async def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("Coach app process is already started")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_root.mkdir(parents=True, exist_ok=True)
        environment = self._environment()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        log_path = self.database_path.parent / "coach-app-process.log"
        with log_path.open("ab") as log:
            self._process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                cwd=self.database_path.parent,
                env=environment,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
        self._base_url = f"http://127.0.0.1:{port}"
        try:
            async with asyncio.timeout(45):
                async with httpx.AsyncClient(timeout=1) as client:
                    while True:
                        if self._process.returncode is not None:
                            raise RuntimeError("Coach backend exited before becoming healthy")
                        try:
                            response = await client.get(f"{self._base_url}/api/health")
                            if response.status_code == 200:
                                return
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.1)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        process = self._process
        self._process = None
        self._base_url = None
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=12)
        except TimeoutError:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=5)
            raise RuntimeError("Coach backend did not stop within 12 seconds") from None

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def __aenter__(self) -> CoachAppProcess:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()
