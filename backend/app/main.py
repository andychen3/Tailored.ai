from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.sources import router as sources_router
from app.core.config import settings
from app.services.source_catalog_store import source_reconciler


class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    """Add Access-Control-Allow-Private-Network for Chrome PNA preflight."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        if request.headers.get("Access-Control-Request-Private-Network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        source_reconciler.reconcile_once(limit=200)
        source_reconciler.start_background_reconcile(
            interval_seconds=settings.source_reconcile_interval_seconds
        )
    except Exception:
        # Reconciliation should not prevent API startup.
        pass
    yield


app = FastAPI(title=settings.app_title, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PrivateNetworkAccessMiddleware)

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(sources_router, prefix="/sources", tags=["sources"])
