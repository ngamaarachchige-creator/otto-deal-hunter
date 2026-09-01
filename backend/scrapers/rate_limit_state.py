"""Shared, persistent rate-limit cooldown tracking, per source host.

Tonight's deep scrape exposed a real bug: when Riyasewana started 429-ing
detail-page requests, that only aborted the *current* batch — the very next
page's scrape started a fresh detail-fetch pass with no memory of the block,
immediately got 429'd again, and repeated that ~60 times across the run. Worse,
each of those code paths (detail_fetch, the listing-page scrapers, the liveness
checker) has its own local state that dies with the process, so nothing was
shared even within a single run, let alone across the manual "Fetch Ads"
button, Copilot-triggered scrapes, and the liveness sweep, all of which can hit
the same host independently.

This persists a simple "don't hit this host again until <timestamp>" cooldown
to a small JSON file on disk, so it survives across processes and across the
different scrape entry points. Cooldown escalates on repeated hits (10min ->
20min -> ... capped at 2h) rather than resetting, since a second 429 shortly
after the first means the first cooldown wasn't long enough yet.
"""
import json
import os
import time
from typing import Optional

_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "rate_limit_state.json"
)

_INITIAL_COOLDOWN_SECONDS = 10 * 60
_MAX_COOLDOWN_SECONDS = 2 * 60 * 60


def _load() -> dict:
    try:
        with open(_STATE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    tmp_path = _STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f)
    os.replace(tmp_path, _STATE_PATH)


def is_cooling_down(host: str) -> Optional[float]:
    """Returns seconds remaining in the cooldown for `host`, or None if clear."""
    state = _load()
    entry = state.get(host)
    if not entry:
        return None
    remaining = entry["until"] - time.time()
    return remaining if remaining > 0 else None


_MIN_SECONDS_BETWEEN_ESCALATIONS = 5.0


def record_rate_limit(host: str) -> float:
    """Records a 429/403 from `host`, escalating the cooldown if one was already
    active or recently expired. Returns the new cooldown length in seconds.

    A batch of concurrent worker threads can each independently hit the block
    within milliseconds of each other — that's one real-world incident, not
    several, so calls within _MIN_SECONDS_BETWEEN_ESCALATIONS of the last
    recorded hit just refresh the existing cooldown rather than re-escalating it."""
    state = _load()
    entry = state.get(host)
    now = time.time()
    if entry and (now - entry.get("last_hit", 0)) < _MIN_SECONDS_BETWEEN_ESCALATIONS:
        return entry["length"]
    if entry and (now - entry.get("last_hit", 0)) < _MAX_COOLDOWN_SECONDS:
        # Still within memory of the last hit — this cooldown wasn't long enough.
        new_length = min(entry["length"] * 2, _MAX_COOLDOWN_SECONDS)
    else:
        new_length = _INITIAL_COOLDOWN_SECONDS
    state[host] = {"until": now + new_length, "length": new_length, "last_hit": now}
    _save(state)
    return new_length
