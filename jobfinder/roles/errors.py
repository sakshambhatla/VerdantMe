from __future__ import annotations


class RateLimitError(Exception):
    """Raised when an LLM API rate limit is hit during filtering or scoring.

    The checkpoint (if enabled) is saved before this is raised so the caller
    can resume from where it left off.
    """
