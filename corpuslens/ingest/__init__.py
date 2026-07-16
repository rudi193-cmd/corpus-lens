"""Adapter registry. An adapter ingests one corpus format and returns
(events, quarantine). Raw absolute timestamps are consumed INSIDE the adapter
to compute day offsets and deltas, then discarded — they never leave on an
Event. Content is consumed to derive process features, then discarded."""
from __future__ import annotations

from ..model import Event, Quarantine

_REGISTRY: dict = {}


def register(name: str):
    def deco(fn):
        _REGISTRY[name] = fn
        return fn
    return deco


def get(name: str):
    if name not in _REGISTRY:
        raise KeyError(f"no adapter {name!r}; available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available() -> list[str]:
    return sorted(_REGISTRY)


from . import claude_code, cursor  # noqa: E402,F401  (registration side effects)
