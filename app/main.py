"""FastAPI application entrypoint.

Phase 1 mounts the reservation REST API. Later phases add the /voice routes on
the same app.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.reservations.router import router as reservations_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic in real deployments. For frictionless local
    # dev we ensure tables exist on startup too; create_all is a no-op when they
    # already do.
    from app.db import create_all

    create_all()
    yield


app = FastAPI(title="Reservation Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reservations_router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
