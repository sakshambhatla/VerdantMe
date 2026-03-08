from __future__ import annotations

from jobfinder.roles.ats.ashby import AshbyFetcher
from jobfinder.roles.ats.base import BaseFetcher
from jobfinder.roles.ats.greenhouse import GreenhouseFetcher
from jobfinder.roles.ats.lever import LeverFetcher
from jobfinder.roles.ats.unsupported import UnsupportedFetcher

_REGISTRY: dict[str, BaseFetcher] = {
    "greenhouse": GreenhouseFetcher(),
    "lever": LeverFetcher(),
    "ashby": AshbyFetcher(),
    "workday": UnsupportedFetcher("workday"),
    "linkedin": UnsupportedFetcher("linkedin"),
    "unknown": UnsupportedFetcher("unknown"),
}


def get_fetcher(ats_type: str) -> BaseFetcher:
    return _REGISTRY.get(ats_type, _REGISTRY["unknown"])
