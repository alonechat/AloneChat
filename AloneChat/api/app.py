"""
AloneChat API - HTTP/WebSocket interaction layer.

This module handles all transport concerns and delegates business logic
to the server layer services.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from AloneChat import __version__
from AloneChat.config import config
from AloneChat.api.middleware import AuthMiddleware, TokenCache
from AloneChat.api.routes import register_routes


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AloneChat API starting up")
    yield
    logger.info("AloneChat API shutting down")


app = FastAPI(
    title="AloneChat API",
    version=__version__,
    description="AloneChat API Server",
    lifespan=lifespan
)

if config.TUNNEL_TRUSTED_HOSTS:
    allowed_hosts = config.TUNNEL_TRUSTED_HOSTS.split(",")

    class TrustedHostMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            host = request.headers.get("host", "").split(":")[0]
            if allowed_hosts != ["*"] and host not in allowed_hosts:
                logger.warning(f"Rejected request with untrusted host: {host}")
                return Response(status_code=400, content="Invalid Host header")
            return await call_next(request)

    app.add_middleware(TrustedHostMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/ping")
async def ping():
    return {"status": "ok"}


app.add_middleware(AuthMiddleware)

register_routes(app)
