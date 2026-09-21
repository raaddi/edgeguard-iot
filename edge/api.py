"""Local read-only HTTP API over telemetry and MQTT control observations."""

import argparse
import logging
from pathlib import Path
import sqlite3
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from contracts.telemetry import TelemetryError
from contracts.commands import CommandError
from edge.observations import control_history
from edge.readings import check_history, device_details, device_history, device_summaries, open_history, recent_history

DeviceId = Annotated[str, ApiPath(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
PageLimit = Annotated[int, Query(ge=1, le=200)]
logger = logging.getLogger(__name__)


class TelemetryRecord(BaseModel):
    id: int
    received_at: str
    received_monotonic_ns: int
    topic: str
    telemetry: dict[str, Any]


class DeviceSummary(BaseModel):
    device_id: str
    message_count: int
    last_received_at: str


class DevicesPage(BaseModel):
    items: list[DeviceSummary]
    has_more: bool
    next_after_device: str


class DeviceDetails(BaseModel):
    device_id: str
    message_count: int
    latest: TelemetryRecord


class TelemetryPage(BaseModel):
    items: list[TelemetryRecord]
    has_more: bool
    next_after_id: int


class RecentPage(BaseModel):
    items: list[TelemetryRecord]
    older_available: bool


class ControlRecord(BaseModel):
    id: int
    kind: str
    received_at: str
    received_monotonic_ns: int
    collector_session_id: str
    mqtt_qos: int
    mqtt_duplicate: bool
    topic: str
    message: dict[str, Any]


class ControlPage(BaseModel):
    items: list[ControlRecord]
    has_more: bool
    next_after_id: int


def create_app(database="data/telemetry.sqlite3"):
    database = Path(database).resolve()
    app = FastAPI(title="EdgeGuard — historia kolektora", version="0.2.0",
                  description="Lokalna historia kolektora. Wpis w bazie nie potwierdza, że węzeł jest online.",
                  redoc_url=None)

    async def unavailable(request: Request, error: Exception):
        logger.error("Collector history unavailable: %s", error)
        return JSONResponse(status_code=503, content={"detail": "Historia kolektora jest niedostępna. Sprawdź bazę i wersję kolektora."})

    for error_type in (sqlite3.Error, OSError, TelemetryError, CommandError):
        app.add_exception_handler(error_type, unavailable)

    @app.get("/health", summary="Dostępność odczytu bazy; nie stan brokera ani węzłów")
    def health() -> dict[str, str]:
        with open_history(database) as db:
            check_history(db)
        return {"status": "ok", "database": "readable"}

    @app.get("/devices", response_model=DevicesPage, summary="Węzły zaobserwowane w zapisanej telemetrii")
    def devices(limit: PageLimit = 100,
                after_device: Annotated[str, Query(pattern=r"^[A-Za-z0-9_-]{0,64}$")] = ""):
        with open_history(database) as db:
            return device_summaries(db, after_device=after_device, limit=limit)

    @app.get("/devices/{device_id}", response_model=DeviceDetails, summary="Ostatnio zapisany raport węzła")
    def device(device_id: DeviceId):
        with open_history(database) as db:
            result = device_details(db, device_id)
        if result is None:
            raise HTTPException(404, "Brak zapisanej telemetrii tego węzła.")
        return result

    @app.get("/devices/{device_id}/telemetry", response_model=TelemetryPage,
             summary="Historia w kolejności zapisu; kursor dotyczy niezmienionej bazy")
    def telemetry(device_id: DeviceId, limit: PageLimit = 100,
                  after_id: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
        with open_history(database) as db:
            result = device_history(db, device_id, after_id=after_id, limit=limit)
        if result is None:
            raise HTTPException(404, "Brak zapisanej telemetrii tego węzła.")
        return result

    @app.get("/devices/{device_id}/telemetry/recent", response_model=RecentPage,
             summary="Ostatnie raporty w kolejności zapisu; ograniczony podgląd konsoli")
    def recent(device_id: DeviceId, limit: PageLimit = 200):
        with open_history(database) as db:
            result = recent_history(db, device_id, limit=limit)
        if result is None:
            raise HTTPException(404, "Brak zapisanej telemetrii tego węzła.")
        return result

    @app.get("/devices/{device_id}/control-history", response_model=ControlPage,
             summary="Odebrane polecenia i wyniki; powtórzenia pozostają osobnymi obserwacjami")
    def control(device_id: DeviceId, limit: PageLimit = 100,
                after_id: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
                command_id: Annotated[str | None, Query(
                    pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")] = None):
        with open_history(database) as db:
            return control_history(db, device_id, after_id=after_id, limit=limit, command_id=command_id)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/telemetry.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
