from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jobfinder.api.routes import companies, logs, resume, roles
from jobfinder.config import load_config
from jobfinder.storage.registry import REGISTRY_FILENAME, load_or_bootstrap_registry
from jobfinder.storage.store import StorageManager
from jobfinder.utils.log_stream import init_log_stream


def reload_registry(app: FastAPI) -> None:
    """Refresh app.state.registry from disk after a discover-companies run."""
    config = load_config()
    store = StorageManager(config.data_dir)
    app.state.registry = (store.read(REGISTRY_FILENAME) or {}).get("companies", [])


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    store = StorageManager(config.data_dir)
    app.state.registry = load_or_bootstrap_registry(store)
    # Keyed by company name; holds AgentSession objects for running browser agents
    app.state.running_agents: dict[str, object] = {}
    init_log_stream(config.data_dir)
    yield


app = FastAPI(title="JobFinder", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(roles.router, prefix="/api")
app.include_router(logs.router, prefix="/api")

# Serve the built React app in production (ui/dist must exist)
_ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
if _ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
