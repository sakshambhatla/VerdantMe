from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from jobfinder.storage.schemas import DiscoveredRole, FlaggedCompany

if TYPE_CHECKING:
    from jobfinder.storage.backend import StorageBackend

CHECKPOINT_FILENAME = "roles_checkpoint.json"


class Checkpoint:
    """Persists role-discovery progress so a rate-limited run can be resumed.

    File layout (``data/roles_checkpoint.json``):

    .. code-block:: json

        {
          "schema_version": 1,
          "created_at": "<iso>",
          "phase": "filtering" | "scoring",
          "raw_roles": [...],
          "flagged_companies": [...],
          "filter_config": {...} | null,
          "filter_batches_done": 12,
          "filter_total_batches": 26,
          "filter_kept_roles": [...],
          "score_criteria": "..." | null,
          "score_batches_done": 0,
          "score_total_batches": 0,
          "partially_scored_roles": []
        }
    """

    def __init__(
        self,
        backend: StorageBackend,
        collection: str = CHECKPOINT_FILENAME,
    ) -> None:
        self._backend = backend
        self._collection = collection
        self._data: dict[str, Any] = {}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def phase(self) -> str:
        return self._data.get("phase", "")

    @property
    def raw_roles(self) -> list[dict]:
        return self._data.get("raw_roles", [])

    @property
    def flagged_companies(self) -> list[dict]:
        return self._data.get("flagged_companies", [])

    @property
    def filter_config(self) -> dict | None:
        return self._data.get("filter_config")

    @property
    def filter_batches_done(self) -> int:
        return self._data.get("filter_batches_done", 0)

    @property
    def filter_total_batches(self) -> int:
        return self._data.get("filter_total_batches", 0)

    @property
    def filter_kept_roles(self) -> list[dict]:
        return self._data.get("filter_kept_roles", [])

    @property
    def score_criteria(self) -> str | None:
        return self._data.get("score_criteria")

    @property
    def score_batches_done(self) -> int:
        return self._data.get("score_batches_done", 0)

    @property
    def partially_scored_roles(self) -> list[dict]:
        return self._data.get("partially_scored_roles", [])

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def exists(self) -> bool:
        return self._backend.exists(self._collection)

    def load(self) -> "Checkpoint":
        data = self._backend.read(self._collection)
        self._data = data if isinstance(data, dict) else {}
        return self

    def _write(self) -> None:
        """Atomic write via the storage backend."""
        self._backend.write(self._collection, self._data)

    def delete(self) -> None:
        self._backend.delete(self._collection)

    # ── Savers ────────────────────────────────────────────────────────────────

    def save_after_fetch(
        self,
        raw_roles: list[DiscoveredRole],
        flagged: list[FlaggedCompany],
        filter_config: dict | None,
        score_criteria: str | None,
        filter_batch_size: int,
        score_batch_size: int,
    ) -> None:
        """Call immediately after ATS fetching completes."""
        total_filter_batches = (
            (len(raw_roles) + filter_batch_size - 1) // filter_batch_size
            if filter_config
            else 0
        )
        self._data = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "phase": "filtering" if filter_config else "scoring",
            "raw_roles": [r.model_dump() for r in raw_roles],
            "flagged_companies": [f.model_dump() for f in flagged],
            "filter_config": filter_config,
            "filter_batches_done": 0,
            "filter_total_batches": total_filter_batches,
            "filter_kept_roles": [],
            "score_criteria": score_criteria,
            "score_batches_done": 0,
            "score_total_batches": 0,
            "partially_scored_roles": [],
        }
        self._write()

    def save_filter_batch(
        self,
        batches_done: int,
        kept_roles: list[DiscoveredRole],
    ) -> None:
        """Call after each successfully completed filter batch."""
        self._data["filter_batches_done"] = batches_done
        self._data["filter_kept_roles"] = [r.model_dump() for r in kept_roles]
        self._write()

    def save_score_batch(
        self,
        batches_done: int,
        roles_so_far: list[DiscoveredRole],
        total_batches: int,
    ) -> None:
        """Call after each successfully completed scoring batch."""
        self._data["phase"] = "scoring"
        self._data["score_batches_done"] = batches_done
        self._data["score_total_batches"] = total_batches
        self._data["partially_scored_roles"] = [r.model_dump() for r in roles_so_far]
        self._write()

    # ── Status summary for API/CLI display ────────────────────────────────────

    def summary(self) -> str:
        phase = self.phase
        if phase == "filtering":
            done = self.filter_batches_done
            total = self.filter_total_batches
            return (
                f"Partial run: {done}/{total} filter batches done, "
                f"{len(self.filter_kept_roles)} roles matched so far"
            )
        if phase == "scoring":
            done = self.score_batches_done
            total = self._data.get("score_total_batches", "?")
            return (
                f"Partial run: filtering complete, "
                f"{done}/{total} scoring batches done"
            )
        return f"Partial run (phase: {phase})"
