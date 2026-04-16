from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
import os

from app.web.api import accounts, config, history, trigger
from app.worker.main import create_scheduler


@asynccontextmanager
async def lifespan(app):
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="CB Auto Subscribe", lifespan=lifespan)

_PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    api_key = os.environ.get("API_KEY", "")
    if api_key and request.url.path not in _PUBLIC_PATHS:
        key = request.headers.get("X-API-Key", "")
        if key != api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(trigger.router, prefix="/api/trigger", tags=["trigger"])

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(os.path.join(_frontend_dir, "index.html"))
