from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jobfinder.api.routes import companies, company_runs, job_runs, logs, motivation, pipeline, resume, roles, settings, waitlist
from jobfinder.config import load_config
from jobfinder.utils.log_stream import init_log_stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    # Keyed by (user_id, company_name); holds AgentSession objects for running browser agents
    app.state.running_agents: dict[tuple[str | None, str], object] = {}
    init_log_stream(config.data_dir)
    yield


app = FastAPI(title="JobFinder", version="5.2.1", lifespan=lifespan)

_cors_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
_cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(resume.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(company_runs.router, prefix="/api")
app.include_router(job_runs.router, prefix="/api")
app.include_router(roles.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(motivation.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(waitlist.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the built React app in production (ui/dist must exist)
_ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
if _ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
