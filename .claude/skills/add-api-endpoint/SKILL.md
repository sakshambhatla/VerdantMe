---
name: add-api-endpoint
description: >
  Guided workflow for adding a new API endpoint to the JobFinder FastAPI backend
  with the correct auth, storage, and config patterns. Use this skill whenever the
  user says "add endpoint", "new API route", "add route", "create endpoint", or any
  similar phrase about adding a new HTTP endpoint to the backend.
---

# Add API Endpoint

Scaffold a new FastAPI endpoint following JobFinder's established patterns.

## Steps

### 1. Gather requirements

Ask the user:
- What does the endpoint do? (CRUD, discovery, streaming, etc.)
- HTTP method + path (e.g., `GET /api/foo`, `POST /api/foo/bar`)
- Does it need auth/storage? (almost always yes)
- Does it call LLMs? (needs api_key resolution)
- Should it also be a CLI command?

### 2. Add request model (if POST/PUT)

Edit `jobfinder/api/models.py`:
```python
class MyNewRequest(BaseModel):
    field: str
    optional_field: int | None = None
```

### 3. Create route handler

Create or edit `jobfinder/api/routes/<name>.py` following this exact pattern:

```python
from fastapi import APIRouter, Depends, HTTPException
from jobfinder.api.auth import get_current_user
from jobfinder.storage import get_storage_backend

router = APIRouter(prefix="/api/<name>", tags=["<name>"])

@router.get("/")
async def my_endpoint(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    # ... your logic here ...
```

**Critical patterns to follow:**
- Always unpack `_auth` — never use `user_id` directly from Depends
- Thread `jwt_token` to `get_storage_backend()` for RLS
- Wrap blocking calls: `await asyncio.to_thread(sync_fn, args)`
- For LLM calls: `api_key = resolve_api_key(config.model_provider, user_id)`
- Config overrides: `config = load_config(**overrides)` with non-None request fields

### 4. Register router

Add to `jobfinder/api/main.py`:
```python
from jobfinder.api.routes.<name> import router as <name>_router
app.include_router(<name>_router)
```

### 5. Add TypeScript types + fetch function

Edit `ui/src/lib/api.ts`:
- Add TypeScript interface matching the response shape
- Add async fetch function using the `api` axios instance

### 6. Mirror in CLI (if applicable)

Add Click command in `jobfinder/cli.py` calling the same core function.

### 7. Update docs

Add the endpoint to `jobfinder/api/CLAUDE.md` endpoint table.

### 8. Verify

Run CLI tests and UI tests to ensure nothing broke.
