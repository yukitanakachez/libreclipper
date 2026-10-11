"""The FastAPI application: API, media, and the built frontend."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from clipper import shell
from clipper.config import AppConfig
from clipper.web import api, media, settings_api
from clipper.web.worker import Worker

UNBUILT = ("<h1>Clipper</h1><p>The frontend isn't built yet. Stop this and run "
           "<code>./start</code>, which builds it (or build it yourself: "
           "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>).</p>")


log = logging.getLogger("clipper.web")
LOCAL_HOSTS = ["127.0.0.1", "localhost"]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_app(cfg: AppConfig, worker: Worker, frontend_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Clipper")
    app.state.cfg = cfg
    app.state.worker = worker

    # Any web page you have open can send requests to localhost. A Host check stops
    # DNS-rebinding pages from reading the API; an Origin check stops other sites
    # from triggering renders, re-picks (a paid Claude call) or Finder windows.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    @app.middleware("http")
    async def same_site_only(request: Request, call_next):
        origin = request.headers.get("origin")
        if (request.method not in SAFE_METHODS and origin is not None
                and urlparse(origin).hostname not in LOCAL_HOSTS):
            return JSONResponse({"detail": "Requests from other websites are refused."},
                                status_code=403)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        """A bug or a broken file: say what it was instead of a bare "Internal Server Error"."""
        log.exception("%s %s failed", request.method, request.url.path)
        return JSONResponse({"detail": f"Clipper hit an unexpected error: {shell.describe_failure(exc)}"},
                            status_code=500)

    app.include_router(api.router)
    app.include_router(media.router)
    app.include_router(settings_api.router)
    # Mounted last: routes are matched in order, so /api and /media win.
    if frontend_dir is not None and (frontend_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def unbuilt() -> str:
            return UNBUILT
    return app
